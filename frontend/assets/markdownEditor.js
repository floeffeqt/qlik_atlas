/**
 * Atlas Shared Markdown Editor
 * Split-view: textarea (left) + live preview (right)
 * Uses marked.js from CDN (loaded lazily if not already present)
 *
 * Usage:
 *   AtlasMarkdownEditor.create(containerId, {
 *     onChange: function(md) {},  // debounced callback
 *     placeholder: 'Write markdown…',
 *     toolbar: true,              // show formatting toolbar
 *     initialValue: ''
 *   });
 *
 *   var editor = AtlasMarkdownEditor.get(containerId);
 *   editor.getValue()
 *   editor.setValue(md)
 *   editor.destroy()
 */
(function () {
  var MARKED_CDN = 'https://cdn.jsdelivr.net/npm/marked@12/marked.min.js';
  var markedReady = null; // Promise that resolves when marked is available
  var instances = {};

  function ensureMarked() {
    if (markedReady) return markedReady;
    if (window.marked) {
      markedReady = Promise.resolve();
      return markedReady;
    }
    markedReady = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = MARKED_CDN;
      s.onload = function () { resolve(); };
      s.onerror = function () { reject(new Error('Failed to load marked.js')); };
      document.head.appendChild(s);
    });
    return markedReady;
  }

  function escHtml(v) {
    return String(v || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderMarkdown(md) {
    if (!window.marked) return escHtml(md);
    try {
      return window.marked.parse(String(md || ''));
    } catch (e) {
      return escHtml(md);
    }
  }

  /* ── Toolbar Actions ── */
  var TOOLBAR_ITEMS = [
    { label: 'H2', action: 'heading2', insert: '## ' },
    { label: 'H3', action: 'heading3', insert: '### ' },
    { label: 'B', action: 'bold', wrap: '**' },
    { label: 'I', action: 'italic', wrap: '_' },
    { label: 'Table', action: 'table', block: '| Spalte 1 | Spalte 2 | Spalte 3 |\n|----------|----------|----------|\n| Wert     | Wert     | Wert     |\n' },
    { label: 'Code', action: 'code', wrap: '`' },
    { label: 'List', action: 'list', insert: '- ' },
  ];

  function applyToolbarAction(textarea, item) {
    var start = textarea.selectionStart;
    var end = textarea.selectionEnd;
    var val = textarea.value;
    var selected = val.substring(start, end);

    if (item.wrap) {
      var wrapped = item.wrap + (selected || 'text') + item.wrap;
      textarea.value = val.substring(0, start) + wrapped + val.substring(end);
      textarea.selectionStart = start + item.wrap.length;
      textarea.selectionEnd = start + item.wrap.length + (selected || 'text').length;
    } else if (item.insert) {
      var lineStart = val.lastIndexOf('\n', start - 1) + 1;
      textarea.value = val.substring(0, lineStart) + item.insert + val.substring(lineStart);
      textarea.selectionStart = textarea.selectionEnd = lineStart + item.insert.length + (start - lineStart);
    } else if (item.block) {
      var prefix = start > 0 && val[start - 1] !== '\n' ? '\n' : '';
      textarea.value = val.substring(0, start) + prefix + item.block + val.substring(end);
      textarea.selectionStart = textarea.selectionEnd = start + prefix.length + item.block.length;
    }

    textarea.focus();
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }

  /* ── Inject scoped CSS (once) ── */
  var cssInjected = false;
  function injectCSS() {
    if (cssInjected) return;
    cssInjected = true;
    var style = document.createElement('style');
    style.textContent = [
      '.md-editor-wrap { display:flex; flex-direction:column; gap:0; border:1px solid rgba(255,255,255,0.15); border-radius:10px; overflow:hidden; background:rgba(255,255,255,0.04); }',
      '.md-editor-toolbar { display:flex; gap:0.25rem; padding:0.4rem 0.6rem; background:rgba(255,255,255,0.06); border-bottom:1px solid rgba(255,255,255,0.1); flex-wrap:wrap; }',
      '.md-editor-toolbar button { padding:0.25rem 0.5rem; background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.12); border-radius:4px; color:rgba(255,255,255,0.7); font-size:0.72rem; font-weight:600; cursor:pointer; font-family:inherit; transition:background 0.15s,color 0.15s; }',
      '.md-editor-toolbar button:hover { background:rgba(255,255,255,0.15); color:#fff; }',
      '.md-editor-split { display:grid; grid-template-columns:1fr 1fr; min-height:200px; }',
      '.md-editor-split textarea { background:transparent; border:none; border-right:1px solid rgba(255,255,255,0.1); color:#fff; padding:0.75rem; font-family:"Fira Code","Cascadia Code",Consolas,monospace; font-size:0.85rem; line-height:1.6; resize:vertical; outline:none; min-height:200px; }',
      '.md-editor-split textarea::placeholder { color:rgba(255,255,255,0.25); }',
      '.md-editor-preview { padding:0.75rem; overflow-y:auto; font-size:0.85rem; line-height:1.6; color:rgba(255,255,255,0.88); max-height:500px; }',
      '.md-editor-preview h1,.md-editor-preview h2,.md-editor-preview h3 { color:#fff; margin:0.8rem 0 0.4rem; }',
      '.md-editor-preview h2 { font-size:1.1rem; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:0.3rem; }',
      '.md-editor-preview h3 { font-size:0.95rem; }',
      '.md-editor-preview p { margin:0.4rem 0; }',
      '.md-editor-preview ul,.md-editor-preview ol { padding-left:1.5rem; margin:0.4rem 0; }',
      '.md-editor-preview code { background:rgba(255,255,255,0.08); padding:0.15rem 0.35rem; border-radius:3px; font-size:0.8rem; }',
      '.md-editor-preview pre { background:rgba(0,0,0,0.3); padding:0.75rem; border-radius:6px; overflow-x:auto; margin:0.5rem 0; }',
      '.md-editor-preview pre code { background:none; padding:0; }',
      '.md-editor-preview table { width:100%; border-collapse:collapse; margin:0.5rem 0; }',
      '.md-editor-preview th,.md-editor-preview td { border:1px solid rgba(255,255,255,0.15); padding:0.4rem 0.6rem; text-align:left; font-size:0.8rem; }',
      '.md-editor-preview th { background:rgba(255,255,255,0.06); font-weight:600; }',
      '.md-editor-preview blockquote { border-left:3px solid rgba(102,126,234,0.5); padding-left:0.75rem; margin:0.5rem 0; color:rgba(255,255,255,0.6); }',
      '.md-editor-status { padding:0.3rem 0.6rem; font-size:0.7rem; color:rgba(255,255,255,0.4); border-top:1px solid rgba(255,255,255,0.08); }',
      '@media (max-width:760px) { .md-editor-split { grid-template-columns:1fr; } .md-editor-split textarea { border-right:none; border-bottom:1px solid rgba(255,255,255,0.1); } }',
    ].join('\n');
    document.head.appendChild(style);
  }

  /* ── Create Editor ── */
  function createEditor(containerId, options) {
    var opts = options || {};
    var container = document.getElementById(containerId);
    if (!container) throw new Error('markdownEditor: container #' + containerId + ' not found');

    injectCSS();

    // Build HTML
    var html = '<div class="md-editor-wrap">';

    // Toolbar
    if (opts.toolbar !== false) {
      html += '<div class="md-editor-toolbar">';
      TOOLBAR_ITEMS.forEach(function (item) {
        html += '<button type="button" data-md-action="' + item.action + '">' + item.label + '</button>';
      });
      if (opts.resetButton) {
        html += '<button type="button" data-md-action="reset" style="margin-left:auto;color:rgba(239,68,68,0.8)">Vorlage zurücksetzen</button>';
      }
      html += '</div>';
    }

    // Split view
    html += '<div class="md-editor-split">';
    html += '<textarea data-md-textarea placeholder="' + escHtml(opts.placeholder || 'Markdown schreiben…') + '">' + escHtml(opts.initialValue || '') + '</textarea>';
    html += '<div class="md-editor-preview" data-md-preview></div>';
    html += '</div>';

    // Status bar
    if (opts.showStatus !== false) {
      html += '<div class="md-editor-status" data-md-status></div>';
    }

    html += '</div>';
    container.innerHTML = html;

    // References
    var textarea = container.querySelector('[data-md-textarea]');
    var preview = container.querySelector('[data-md-preview]');
    var statusEl = container.querySelector('[data-md-status]');

    // Debounced rendering & callback
    var debounceTimer = null;
    function scheduleUpdate() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        preview.innerHTML = renderMarkdown(textarea.value);
        if (opts.onChange) opts.onChange(textarea.value);
      }, 150);
    }

    textarea.addEventListener('input', scheduleUpdate);

    // Toolbar click handlers
    container.querySelectorAll('[data-md-action]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        var actionName = this.getAttribute('data-md-action');
        if (actionName === 'reset' && opts.onReset) {
          opts.onReset();
          return;
        }
        var item = TOOLBAR_ITEMS.find(function (t) { return t.action === actionName; });
        if (item) applyToolbarAction(textarea, item);
      });
    });

    // Initial render
    ensureMarked().then(function () {
      preview.innerHTML = renderMarkdown(textarea.value);
    });

    var instance = {
      getValue: function () { return textarea.value; },
      setValue: function (md) {
        textarea.value = md || '';
        preview.innerHTML = renderMarkdown(md);
      },
      setStatus: function (text) {
        if (statusEl) statusEl.textContent = text || '';
      },
      focus: function () { textarea.focus(); },
      getTextarea: function () { return textarea; },
      destroy: function () {
        clearTimeout(debounceTimer);
        container.innerHTML = '';
        delete instances[containerId];
      }
    };

    instances[containerId] = instance;
    return instance;
  }

  function getEditor(containerId) {
    return instances[containerId] || null;
  }

  window.AtlasMarkdownEditor = {
    create: createEditor,
    get: getEditor,
    ensureMarked: ensureMarked,
    renderMarkdown: renderMarkdown
  };
})();
