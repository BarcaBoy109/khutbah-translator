import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const template = await readFile(new URL('../templates/index.html', import.meta.url), 'utf8');

test('translation workspace exposes the core Arabic and English surfaces', () => {
  assert.match(template, /id="arabicText"/);
  assert.match(template, /id="englishText"/);
  assert.match(template, /\.lang='ar-SA'/);
  assert.match(template, /action="\/upload"/);
});

test('sermon context features are present', () => {
  assert.match(template, /id="glossary"/);
  assert.match(template, /quoteCues/);
  assert.match(template, /التقوى/);
  assert.match(template, /Qur’an quotation cue/);
});

test('operator controls are wired', () => {
  assert.match(template, /id="listenBtn"/);
  assert.match(template, /id="clearTranscript"/);
  assert.match(template, /khutbah-arabic-transcript\.txt/);
  assert.match(template, /Copy latest/);
});
