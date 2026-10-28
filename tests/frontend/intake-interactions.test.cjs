const test = require("node:test");
const assert = require("node:assert/strict");
const {
  createReplyFormatter, filesFromTransfer, createFileQueue,
} = require("../../career_agent/web/static/intake-interactions.js");

test("repeated guidance is shown once without dropping requested facts", () => {
  const format = createReplyFormatter();
  const first = format("为了生成可用的简历，还需要：请填写姓名。你可以直接用一句话回答；不想提供的项目也可以直接告诉我跳过。");
  const next = format("已记录学校。 为了生成可用的简历，还需要：请至少填写一项技能。你可以直接用一句话回答；不想提供的项目也可以直接告诉我跳过。");
  assert.match(first, /不想提供/);
  assert.doesNotMatch(next, /为了生成|一句话回答|不想提供/);
  assert.match(next, /技能/);
  assert.match(next, /已记录学校/);
});

test("optional transition and skip hints do not repeat on later topics", () => {
  const format = createReplyFormatter();
  const first = format("基础信息已经整理好。接下来补充可选信息（1/7）：可以补充现居城市；没有可以回复“跳过”。也可以回复“全部跳过”。");
  const next = format("基础信息已经整理好。接下来补充可选信息（2/7）：有没有相关课程？没有可以回复“跳过”。也可以回复“全部跳过”。");
  assert.match(first, /全部跳过/);
  assert.doesNotMatch(next, /基础信息|全部跳过|没有可以回复/);
  assert.match(next, /课程/);
});

test("drop and clipboard file payloads share extraction and ignore ordinary text", () => {
  const photo = {name: "photo.png", size: 10, lastModified: 1, type: "image/png"};
  assert.deepEqual(filesFromTransfer({files: [photo], items: [
    {kind: "file", getAsFile: () => photo}, {kind: "string", getAsFile: () => null},
  ]}), [photo]);
  assert.deepEqual(filesFromTransfer({files: [], items: [{kind: "string", type: "text/plain"}]}), []);
  assert.deepEqual(filesFromTransfer({items: [{kind: "file", getAsFile: () => photo}]}), [photo]);
});

test("shared queue serializes drop/paste, validates types and avoids duplicates", async () => {
  let pending = [];
  const errors = [];
  const readNames = [];
  const enqueue = createFileQueue({
    getQueue: () => pending,
    setQueue: files => { pending = files; },
    notify: message => errors.push(message),
    readFile: async file => { readNames.push(file.name); return file.data; },
  });
  const photo = {name: "photo.png", type: "image/png", size: 10, data: "data:image/png;base64,a"};
  const pasted = {name: "image.png", type: "image/png", size: 10, data: "data:image/png;base64,b"};
  await Promise.all([enqueue([photo]), enqueue([pasted, photo])]);
  assert.equal(pending.length, 2);
  await enqueue([
    {name: "large.png", type: "image/png", size: 11 * 1024 * 1024},
    {name: "app.exe", type: "application/x-msdownload", size: 10},
  ]);
  assert.equal(pending.length, 2);
  assert.equal(errors.length, 2);
  assert.ok(!readNames.includes("large.png"));
  assert.ok(!readNames.includes("app.exe"));
  assert.deepEqual(pending.map(file => file.filename), ["photo.png", "image.png"]);
});

test("queue limits five files and recovers after a file read error", async () => {
  let pending = [];
  const errors = [];
  const enqueue = createFileQueue({
    getQueue: () => pending,
    setQueue: files => { pending = files; },
    notify: message => errors.push(message),
    readFile: async file => { if (file.name === "bad.png") throw new Error("read error"); return file.name; },
  });
  const file = name => ({name, type: "image/png", size: 1});
  await enqueue([file("bad.png"), file("1.png")]);
  await enqueue([2, 3, 4, 5, 6].map(i => file(`${i}.png`)));
  assert.equal(pending.length, 5);
  assert.equal(errors.length, 2);
  assert.equal(pending[0].filename, "1.png");
});
