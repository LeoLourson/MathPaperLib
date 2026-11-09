/**
 * MathPaperLib as one DSH plugin: the MCP server `mathpaperlib`, the skills of the repository
 * (`../skills/<name>/SKILL.md`, the same files Claude Code reads) and a two-line section of the
 * system prompt with the library and the files waiting in its inbox.
 *
 * The library is found by the rule of the Python package: `MATHPAPERLIB_HOME`, else
 * `~/Literature`. A profile that keeps it elsewhere sets the variable for both entries.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const name = 'dsh-mathpaperlib';
export const inject = ['skills', 'systemPrompt'];

const here = dirname(fileURLToPath(import.meta.url));

/** The library folder: the rule of `mathpaperlib.paths.configure` without a project. */
export function defaultLibrary(env = process.env, home = homedir()) {
  return env.MATHPAPERLIB_HOME || join(home, 'Literature');
}

/** Split one SKILL.md into its frontmatter fields and its body. */
export function parseSkill(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
  const fields = {};
  if (match) {
    for (const line of match[1].split(/\r?\n/)) {
      const at = line.indexOf(':');
      if (at <= 0) continue;
      let value = line.slice(at + 1).trim();
      if (/^(['"]).*\1$/.test(value)) value = value.slice(1, -1);
      fields[line.slice(0, at).trim()] = value;
    }
  }
  return { fields, body: (match === null ? text : text.slice(match[0].length)).trim() };
}

/** Every skill of the repository, skipping folders whose SKILL.md cannot name one. */
export function loadSkills(directory = join(here, '..', 'skills')) {
  let folders;
  try {
    folders = readdirSync(directory).sort();
  } catch {
    return [];
  }
  const skills = [];
  for (const folder of folders) {
    let text;
    try {
      text = readFileSync(join(directory, folder, 'SKILL.md'), 'utf8');
    } catch {
      continue;
    }
    const { fields, body } = parseSkill(text);
    if (typeof fields.name === 'string' && fields.description && body) {
      skills.push({
        name: fields.name,
        description: fields.description,
        ...fields.whenToUse === undefined ? {} : { whenToUse: fields.whenToUse },
        content: body,
      });
    }
  }
  return skills;
}

function count(file) {
  try {
    return JSON.parse(readFileSync(file, 'utf8')).length;
  } catch {
    return 0;
  }
}

function waiting(folder) {
  try {
    return readdirSync(folder).filter((file) => file.toLowerCase().endsWith('.pdf')).length;
  } catch {
    return 0;
  }
}

/** The section text: where the library is, how many papers it holds, what waits in the inbox. */
export function describe(library) {
  const inbox = join(library, 'inbox');
  const pending = waiting(inbox);
  return [
    `MathPaperLib: library ${library}, papers ${count(join(library, 'library.json'))}; inbox ${inbox}` +
      (pending ? `, ${pending} PDF waiting: call inbox.` : '.'),
    'Papers, citations, DOI, full texts: tools of the mathpaperlib server (start with where), not web search.',
  ].join('\n');
}

export function apply(ctx, config = {}) {
  const library = config.library ?? defaultLibrary();

  // Disposers are chained to the plugin's lifetime: disabling it removes its skills.
  ctx.effect(() => {
    const disposers = loadSkills().map((skill) => ctx.skills.register({ ...skill, source: 'runtime' }));
    return () => {
      for (const dispose of disposers) dispose();
    };
  }, 'dsh-mathpaperlib: skills');

  ctx.systemPrompt.section({
    name: 'mathpaperlib',
    order: 1010,
    text: () => describe(library),
  });
}
