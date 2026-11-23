// Run a rendered main.js against a fake KWin scripting API.
// Usage: node fake_kwin.js <main.js> <scenario.json>
// The scenario holds windows (bottom to top), the active window index and the
// chords to press. Prints the events as JSON.
const fs = require("fs");
const vm = require("vm");

const [script, scenarioPath] = process.argv.slice(2);
const scenario = JSON.parse(fs.readFileSync(scenarioPath, "utf8"));
const events = [];
const handlers = {};

const windows = scenario.windows.map(function (w, i) {
  return {
    id: i,
    resourceName: w.resourceName || "",
    resourceClass: w.resourceClass || "",
    minimized: !!w.minimized,
    noBorder: false,
  };
});

const workspace = {
  stackingOrder: windows,
  activeWindow: scenario.active === null ? null : windows[scenario.active],
  windowAdded: { connect: function () {} },
};

const sandbox = {
  workspace: workspace,
  JSON: JSON,
  registerShortcut: function (name, text, key, callback) {
    handlers[name] = callback;
    events.push(["register", name, key]);
  },
  callDBus: function (service, path, iface, method, ...args) {
    if (method === "Log") return;
    events.push(
      ["dbus", service, path, iface, method].concat(args.filter((a) => typeof a !== "function")),
    );
  },
};

vm.runInNewContext(fs.readFileSync(script, "utf8"), sandbox);
for (const name of scenario.press) {
  handlers[name]();
}
console.log(
  JSON.stringify({
    events: events,
    active: workspace.activeWindow === null ? null : workspace.activeWindow.id,
    windows: windows.map(function (w) {
      return { minimized: w.minimized, noBorder: w.noBorder };
    }),
  }),
);
