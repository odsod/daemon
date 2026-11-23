(function() {
  function getName(tile) {
    var names = Array.from(tile.querySelectorAll('.notranslate'))
      .map(function(n) { return n.innerText.trim(); })
      .filter(function(s) {
        return s.length > 2 && s.length < 50
          && s[0] === s[0].toUpperCase()
          && s.includes(' ');
      });
    return names[0] || null;
  }
  return JSON.stringify(
    Array.from(document.querySelectorAll('[data-participant-id]')).map(function(t) {
      var name = getName(t);
      if (!name) return null;
      var speaking = !!t.querySelector('.__SPEAKING_CLASS__')
        || !!t.closest('.__SPEAKING_CLASS__');
      return {name: name, speaking: speaking};
    }).filter(Boolean)
  );
})()
