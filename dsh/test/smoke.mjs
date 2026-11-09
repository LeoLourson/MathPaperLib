/**
 * The plugin without a running DSH: the skills it registers, the prompt section it adds and
 * the patch it ships. Run with `node dsh/test/smoke.mjs`.
 */

import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { apply, defaultLibrary } from '../index.js';

const here = dirname(fileURLToPath(import.meta.url));

function context() {
  const skills = [];
  const sections = [];
  const disposers = [];
  const ctx = {
    effect(effect) {
      disposers.push(effect());
      return () => {};
    },
    skills: {
      register(skill) {
        skills.push(skill);
        return () => {
          const at = skills.indexOf(skill);
          if (at >= 0) skills.splice(at, 1);
        };
      },
    },
    systemPrompt: {
      section(section) {
        sections.push(section);
      },
    },
  };
  return { ctx, skills, sections, disposers };
}

// The library follows the rule of the Python package, and the patch names no machine.
assert.equal(defaultLibrary({ MATHPAPERLIB_HOME: 'D:\\papers' }, 'H'), 'D:\\papers');
assert.equal(defaultLibrary({}, 'H'), join('H', 'Literature'));
const patch = readFileSync(join(here, '..', 'cordis.patch.yml'), 'utf8');
assert.doesNotMatch(patch, /(^|[\s'"])[A-Za-z]:[\\/]|\/home\/|\/Users\//m, 'an absolute path in the patch');
assert.match(patch, /serverName: mathpaperlib/);

const library = mkdtempSync(join(tmpdir(), 'dsh-mathpaperlib-'));
try {
  const first = context();
  apply(first.ctx, { library });
  assert.equal(first.sections.length, 1, 'the plugin adds one prompt section');
  const [section] = first.sections;
  assert.equal(section.name, 'mathpaperlib');
  let lines = section.text({}).split('\n');
  assert.equal(lines.length, 2, 'the prompt section is two lines');
  assert.ok(lines[0].includes(library) && lines[0].includes('papers 0'), 'the library and its size');
  assert.ok(!lines[0].includes('waiting'), 'nothing waits in an absent inbox');

  writeFileSync(join(library, 'library.json'), JSON.stringify([{ filename: 'A 2020 - X.pdf' }]));
  mkdirSync(join(library, 'inbox'));
  writeFileSync(join(library, 'inbox', 'download.pdf'), '%PDF-');
  lines = section.text({}).split('\n');
  assert.ok(lines[0].includes('papers 1'), 'the inventory is re-read');
  assert.ok(lines[0].includes('1 PDF waiting: call inbox'), 'files in the inbox are announced');

  const names = first.skills.map((skill) => skill.name).sort();
  assert.deepEqual(names, ['literature', 'transcribe-paper']);
  for (const skill of first.skills) {
    assert.ok(skill.description.length > 0, `${skill.name}: description`);
    assert.ok(skill.content.length > 0, `${skill.name}: content`);
    assert.equal(skill.source, 'runtime');
  }
  for (const dispose of first.disposers) dispose();
  assert.equal(first.skills.length, 0, 'skills are disposed with the plugin');
} finally {
  rmSync(library, { recursive: true, force: true });
}

for (const locale of ['ru', 'en']) {
  const card = JSON.parse(readFileSync(join(here, '..', 'locale', `${locale}.json`), 'utf8'));
  assert.ok(card.meta.title, `${locale}: title`);
  assert.ok(card.meta.description, `${locale}: description`);
}

console.log('ok: 2 skills, 2 prompt lines, inbox notice, disposal, both locales');
