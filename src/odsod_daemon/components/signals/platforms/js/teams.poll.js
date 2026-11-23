(function() {
  function getName(el) {
    var node = el.parentElement;
    for (var i = 0; i < 3 && node; i++) {
      var tid = node.getAttribute('data-tid');
      if (tid && tid.length > 2 && tid.length < 80
          && tid.indexOf('video-item-container') !== 0) {
        return tid;
      }
      node = node.parentElement;
    }
    return null;
  }
  return JSON.stringify(
    Array.from(document.querySelectorAll('[data-tid="voice-level-stream-outline"]'))
      .map(function(el) {
        var name = getName(el);
        if (!name) return null;
        var speaking = el.classList.contains('__SPEAKING_CLASS__');
        return {name: name, speaking: speaking};
      })
      .filter(Boolean)
  );
})()
