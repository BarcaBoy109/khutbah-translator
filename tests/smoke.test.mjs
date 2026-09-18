import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const template = await readFile(new URL('../templates/index.html', import.meta.url), 'utf8');
const samples = JSON.parse(await readFile(new URL('./fixtures/sermon-samples.json', import.meta.url), 'utf8'));

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

test('Arabic sermon evaluation fixture is loaded and structurally valid', () => {
  assert.equal(samples.length, 5);
  for (const sample of samples) {
    assert.ok(sample.id);
    assert.ok(sample.arabic);
    assert.ok(sample.referenceEnglish);
    assert.ok(Array.isArray(sample.expectedTerms));
  }
  assert.ok(samples.some(sample => sample.quoteCue === 'Qur’an quotation cue'));
  assert.ok(samples.some(sample => sample.quoteCue === 'Hadith quotation cue'));
});
