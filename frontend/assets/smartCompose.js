/**
 * Atlas Smart Compose
 * Structured-input editors that auto-assemble clean Markdown for the API.
 * No Markdown knowledge required from the user.
 *
 * API:
 *   var editor = AtlasSmartCompose.readme(containerId, opts)
 *   var editor = AtlasSmartCompose.log(containerId, opts)
 *
 *   opts (readme): { readmeType: 'app_readme'|'project_readme', initialValue, onChange }
 *   opts (log):    { initialValue }
 *
 *   editor.getValue()              → Markdown string for API
 *   editor.setValue(md)            → parse existing Markdown back into fields
 *   editor.insertSection(key, txt) → overwrite a named section (used by DS-chips)
 *   editor.clear()                 → clear all fields
 *   editor.destroy()               → remove DOM + cleanup
 */
(function () {
  'use strict';

  // ── Section definitions ─────────────────────────────────────────────

  var README_SECTIONS_APP = [
    {
      key: 'beschreibung', heading: 'Was macht diese App?',
      placeholder: 'Kurze Beschreibung des Zwecks und der Inhalte der App…',
      rows: 3,
    },
    {
      key: 'datenquellen', heading: 'Datenquellen',
      placeholder: 'Welche Datenquellen werden genutzt? (oder Quellen oben auswählen und einfügen)',
      rows: 3,
    },
    {
      key: 'reload', heading: 'Reload / Automatisierung',
      placeholder: 'Wann und wie wird die App geladen? Zeitplan, Trigger, Abhängigkeiten…',
      rows: 2,
    },
    {
      key: 'ansprechpartner', heading: 'Ansprechpartner',
      placeholder: 'Name, Rolle, Kontakt…',
      rows: 2,
    },
    {
      key: 'probleme', heading: 'Bekannte Probleme',
      placeholder: 'Bekannte Einschränkungen oder offene Punkte…',
      rows: 2, optional: true,
    },
  ];

  var README_SECTIONS_PROJECT = [
    {
      key: 'beschreibung', heading: 'Tenant-Übersicht',
      placeholder: 'Wofür wird dieser Tenant genutzt? Wer sind die Hauptnutzer?',
      rows: 3,
    },
    {
      key: 'architektur', heading: 'Architektur',
      placeholder: 'Wie ist der Tenant strukturiert? Bereiche, Spaces, Datenflüsse…',
      rows: 3,
    },
    {
      key: 'reload', heading: 'Reload-Automation',
      placeholder: 'Wie und wann werden Apps automatisch geladen?',
      rows: 2,
    },
    {
      key: 'ansprechpartner', heading: 'Ansprechpartner',
      placeholder: 'Wer ist verantwortlich? Name, Rolle, Kontakt…',
      rows: 2,
    },
    {
      key: 'entscheidungen', heading: 'Entscheidungen',
      placeholder: 'Wichtige Architektur- oder Technologieentscheidungen…',
      rows: 3, optional: true,
    },
    {
      key: 'einschraenkungen', heading: 'Einschränkungen',
      placeholder: 'Bekannte Limitierungen oder Risiken…',
      rows: 2, optional: true,
    },
  ];

  var LOG_SECTIONS = [
    {
      key: 'was', label: 'Was wurde gemacht / entschieden?',
      placeholder: 'Kurze, klare Beschreibung des Vorgangs…',
      rows: 3,
    },
    {
      key: 'warum', label: 'Warum / Begründung',
      placeholder: 'Hintergrund, Kontext oder Begründung…',
      rows: 2, optional: true,
    },
  ];

  // ── Markdown assembly ───────────────────────────────────────────────

  function buildReadmeMarkdown(sections, values) {
    return sections
      .map(function (s) {
        var val = (values[s.key] || '').trim();
        return val ? '## ' + s.heading + '\n\n' + val : '';
      })
      .filter(Boolean)
      .join('\n\n');
  }

  function buildLogMarkdown(values) {
    var parts = [];
    if ((values.was   || '').trim()) parts.push('**Was:** '   + values.was.trim());
    if ((values.warum || '').trim()) parts.push('**Warum:** ' + values.warum.trim());
    return parts.join('\n\n');
  }

  // ── Markdown parsing ────────────────────────────────────────────────

  function parseReadmeSections(md, sections) {
    var result = {};
    sections.forEach(function (s) { result[s.key] = ''; });

    var normalized = String(md || '').replace(/\r\n/g, '\n');
    // Split on lines that start a new ## section
    var chunks = normalized.split(/\n(?=## )/);
    chunks.forEach(function (chunk) {
      if (!chunk.startsWith('## ')) return;
      var nl = chunk.indexOf('\n');
      var heading = (nl === -1 ? chunk : chunk.slice(0, nl)).replace(/^##\s*/, '').trim();
      var body    = nl === -1 ? '' : chunk.slice(nl + 1).trim();
      sections.forEach(function (s) {
        if (heading.toLowerCase() === s.heading.toLowerCase()) {
          result[s.key] = body;
        }
      });
    });
    return result;
  }

  function parseLogSections(md) {
    var result = { was: '', warum: '' };
    String(md || '').replace(/\r\n/g, '\n').split('\n\n').forEach(function (block) {
      var m;
      if ((m = block.match(/^\*\*Was:\*\*\s*([\s\S]*)/)))   result.was   = m[1].trim();
      if ((m = block.match(/^\*\*Warum:\*\*\s*([\s\S]*)/))) result.warum = m[1].trim();
    });
    return result;
  }

  // ── CSS (injected once) ─────────────────────────────────────────────

  var cssInjected = false;
  function injectCSS() {
    if (cssInjected) return;
    cssInjected = true;
    var style = document.createElement('style');
    style.textContent = [
      '.sc-wrap { display:flex; flex-direction:column; gap:0.9rem; }',
      '.sc-field { display:flex; flex-direction:column; gap:0.3rem; }',
      '.sc-label {',
      '  font-size:0.73rem; font-weight:700; color:rgba(255,255,255,0.45);',
      '  letter-spacing:0.06em; text-transform:uppercase;',
      '}',
      '.sc-optional {',
      '  font-weight:400; color:rgba(255,255,255,0.25); margin-left:0.35rem;',
      '  text-transform:none; font-size:0.7rem; letter-spacing:0;',
      '}',
      '.sc-textarea, .sc-input {',
      '  width:100%; background:rgba(255,255,255,0.06);',
      '  border:1px solid rgba(255,255,255,0.12); border-radius:8px;',
      '  color:#fff; padding:0.6rem 0.75rem;',
      '  font-size:0.88rem; font-family:inherit; line-height:1.55;',
      '  resize:vertical; outline:none; transition:border-color 0.15s;',
      '  box-sizing:border-box;',
      '}',
      '.sc-input { resize:none; }',
      '.sc-textarea:focus, .sc-input:focus { border-color:rgba(102,126,234,0.65); }',
      '.sc-textarea::placeholder, .sc-input::placeholder { color:rgba(255,255,255,0.2); }',
    ].join('\n');
    document.head.appendChild(style);
  }

  // ── Helpers ─────────────────────────────────────────────────────────

  function escHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderFields(container, fields, useFieldLabel) {
    var html = '<div class="sc-wrap">';
    fields.forEach(function (s) {
      var label = useFieldLabel ? s.label : s.heading;
      html += '<div class="sc-field">';
      html += '<label class="sc-label">' + escHtml(label);
      if (s.optional) html += '<span class="sc-optional">(optional)</span>';
      html += '</label>';
      if (s.rows === 1) {
        html += '<input class="sc-input" type="text" data-sc-key="' + escHtml(s.key) + '"'
             + ' placeholder="' + escHtml(s.placeholder || '') + '" />';
      } else {
        html += '<textarea class="sc-textarea" data-sc-key="' + escHtml(s.key) + '"'
             + ' rows="' + (s.rows || 3) + '"'
             + ' placeholder="' + escHtml(s.placeholder || '') + '"></textarea>';
      }
      html += '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }

  function collectValues(container) {
    var vals = {};
    container.querySelectorAll('[data-sc-key]').forEach(function (el) {
      vals[el.dataset.scKey] = el.value;
    });
    return vals;
  }

  function applyValues(container, vals) {
    container.querySelectorAll('[data-sc-key]').forEach(function (el) {
      el.value = vals[el.dataset.scKey] || '';
    });
  }

  // ── Public: AtlasSmartCompose.readme() ──────────────────────────────

  function createReadme(containerId, opts) {
    opts = opts || {};
    var container = document.getElementById(containerId);
    if (!container) throw new Error('AtlasSmartCompose.readme: #' + containerId + ' not found');
    injectCSS();

    var sections = opts.readmeType === 'project_readme'
      ? README_SECTIONS_PROJECT
      : README_SECTIONS_APP;

    renderFields(container, sections, false);

    var debounceTimer = null;
    function scheduleChange() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        if (opts.onChange) opts.onChange(instance.getValue());
      }, 200);
    }
    container.querySelectorAll('[data-sc-key]').forEach(function (el) {
      el.addEventListener('input', scheduleChange);
    });

    var instance = {
      getValue: function () {
        return buildReadmeMarkdown(sections, collectValues(container));
      },
      setValue: function (md) {
        applyValues(container, parseReadmeSections(md, sections));
      },
      /** Directly overwrite a named section — used by the DS-chips "In README einfügen" button */
      insertSection: function (key, text) {
        var el = container.querySelector('[data-sc-key="' + key + '"]');
        if (!el) return;
        el.value = text;
        scheduleChange();
      },
      clear: function () {
        container.querySelectorAll('[data-sc-key]').forEach(function (el) { el.value = ''; });
      },
      destroy: function () {
        clearTimeout(debounceTimer);
        container.innerHTML = '';
      },
    };

    if (opts.initialValue) instance.setValue(opts.initialValue);
    return instance;
  }

  // ── Public: AtlasSmartCompose.log() ─────────────────────────────────

  function createLog(containerId, opts) {
    opts = opts || {};
    var container = document.getElementById(containerId);
    if (!container) throw new Error('AtlasSmartCompose.log: #' + containerId + ' not found');
    injectCSS();

    renderFields(container, LOG_SECTIONS, true);

    var instance = {
      /** Returns structured fields as an object — use this for API calls */
      getValues: function () {
        var v = collectValues(container);
        return {
          was:   (v.was   || '').trim(),
          warum: (v.warum || '').trim() || null,
        };
      },
      /** Backward-compat: returns only the "was" field as a plain string */
      getValue: function () {
        return (collectValues(container).was || '').trim();
      },
      setValue: function (md) {
        applyValues(container, parseLogSections(md));
      },
      clear: function () {
        container.querySelectorAll('[data-sc-key]').forEach(function (el) { el.value = ''; });
      },
      destroy: function () {
        container.innerHTML = '';
      },
    };

    if (opts.initialValue) instance.setValue(opts.initialValue);
    return instance;
  }

  // ── Export ───────────────────────────────────────────────────────────

  window.AtlasSmartCompose = {
    readme: createReadme,
    log:    createLog,
  };

}());
