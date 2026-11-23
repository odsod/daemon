// Rendered by the shortcuts component. The list comes from shortcuts.json.
const shortcuts = /*@shortcuts@*/ [];

const SERVICE = "io.github.odsod.daemon.session";
const PATH = "/io/github/odsod/daemon/shortcuts";
const INTERFACE = "io.github.odsod.daemon.Shortcuts";

function log(...args) {
  callDBus(SERVICE, PATH, INTERFACE, "Log", JSON.stringify(args));
}

function run(shortcut) {
  callDBus(SERVICE, PATH, INTERFACE, "Run", shortcut.actionId[1]);
}

function matchesShortcut(window, shortcut) {
  if (shortcut.resourceName) {
    return window.resourceName.toString() === shortcut.resourceName;
  } else if (shortcut.resourceClass) {
    return window.resourceClass.toString() === shortcut.resourceClass;
  } else if (shortcut.resourceClassIncludes) {
    return window.resourceClass.toString().includes(shortcut.resourceClassIncludes);
  }
  return false;
}

function findWindow(shortcut) {
  // Stacking order is bottom to top: the window used last is on top.
  return workspace.stackingOrder
    .slice()
    .reverse()
    .find(function (window) {
      return matchesShortcut(window, shortcut);
    });
}

function logWindows() {
  log("printing debug output");
  workspace.stackingOrder.forEach(function (window) {
    log("resourceName[", window.resourceName, "]", "resourceClass[", window.resourceClass, "]");
  });
}

function toggleApp(shortcut) {
  const window = findWindow(shortcut);
  if (!window) {
    run(shortcut);
  } else if (window.minimized) {
    window.minimized = false;
    workspace.activeWindow = window;
  } else if (workspace.activeWindow != window) {
    workspace.activeWindow = window;
  } else {
    window.minimized = true;
  }
}

function handle(shortcut) {
  log("handling shortcut", shortcut.actionId[1]);
  if (shortcut.kind === "debug") {
    logWindows();
  } else if (shortcut.kind === "app") {
    toggleApp(shortcut);
  } else {
    run(shortcut);
  }
}

shortcuts.forEach(function (shortcut) {
  if (shortcut.kind === "builtin") {
    return;
  }
  registerShortcut(shortcut.actionId[1], shortcut.actionId[3], shortcut.key, function () {
    handle(shortcut);
  });
});

callDBus(SERVICE, PATH, INTERFACE, "Configure", function () {
  log("shortcuts configured");
});

function applyWindowRules(window) {
  shortcuts.forEach(function (shortcut) {
    if (shortcut.noBorder && matchesShortcut(window, shortcut)) {
      window.noBorder = true;
    }
  });
}

workspace.stackingOrder.forEach(applyWindowRules);
workspace.windowAdded.connect(applyWindowRules);
