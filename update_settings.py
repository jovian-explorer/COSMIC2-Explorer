import re
with open('frontend/js/main.js', 'r', encoding='utf-8') as f:
    content = f.read()

new_body = """function settingsBody() {
  const container = el('div', {class: 'stack'});
  
  const form = el('form', {onsubmit: async (e) => {
    e.preventDefault();
    const patch = {
      ui_theme: $('#s-theme').value,
      ui_font_size: parseInt($('#s-font').value, 10),
      ui_mode: $('#s-mode').value,
      plot_theme: $('#s-plot-theme').value,
      plot_dpi: parseInt($('#s-plot-dpi').value, 10),
      units_temperature: $('#s-units-temp').value,
      qc_require_good: $('#s-qc').checked,
      default_stream: $('#s-stream').value
    };
    try {
      const updated = await api.saveSettings(patch);
      state.meta.settings = updated;
      applySettings(updated);
      toast('Settings saved');
    } catch (err) {
      toast('Error saving settings: ' + err, 'bad');
    }
  }});

  form.append(
    el('label', {}, 'Interface Theme ',
      el('select', {id: 's-theme'},
        el('option', {value: 'light', selected: state.meta.settings.ui_theme === 'light'}, 'Light / Day'),
        el('option', {value: 'dark', selected: state.meta.settings.ui_theme === 'dark'}, 'Dark / Night')
      )
    ),
    el('label', {}, 'Font Size (px) ',
      el('input', {type: 'number', id: 's-font', value: state.meta.settings.ui_font_size || 14, min: 10, max: 24})
    ),
    el('label', {}, 'Interface Mode ',
      el('select', {id: 's-mode'},
        el('option', {value: 'educational', selected: state.meta.settings.ui_mode !== 'research'}, 'Educational (More explanations)'),
        el('option', {value: 'research', selected: state.meta.settings.ui_mode === 'research'}, 'Research (Compact interface)')
      )
    ),
    el('hr'),
    el('h3', {}, 'Plot Appearance'),
    el('label', {}, 'Plot Theme ',
      el('select', {id: 's-plot-theme'},
        el('option', {value: 'light', selected: state.meta.settings.plot_theme === 'light'}, 'Light'),
        el('option', {value: 'dark', selected: state.meta.settings.plot_theme === 'dark'}, 'Dark')
      )
    ),
    el('label', {}, 'Plot DPI (Export) ',
      el('input', {type: 'number', id: 's-plot-dpi', value: state.meta.settings.plot_dpi || 300, min: 72, max: 1200, step: 10})
    ),
    el('hr'),
    el('h3', {}, 'Science Defaults'),
    el('label', {}, 'Default Stream ',
      el('select', {id: 's-stream'},
        el('option', {value: 'nrt', selected: state.meta.settings.default_stream === 'nrt'}, 'Near Real-Time (nrt)'),
        el('option', {value: 'postcal', selected: state.meta.settings.default_stream === 'postcal'}, 'Post-Processed (postcal)')
      )
    ),
    el('label', {}, 'Temperature Units ',
      el('select', {id: 's-units-temp'},
        el('option', {value: 'C', selected: state.meta.settings.units_temperature === 'C'}, 'Celsius (\u00b0C)'),
        el('option', {value: 'K', selected: state.meta.settings.units_temperature === 'K'}, 'Kelvin (K)')
      )
    ),
    el('label', {class: 'check'},
      el('input', {type: 'checkbox', id: 's-qc', checked: state.meta.settings.qc_require_good}),
      ' Require Good QC by default'
    ),
    el('hr'),
    el('button', {class: 'primary', type: 'submit'}, 'Save Settings')
  );

  container.append(form);
  return container;
}"""

content = re.sub(r'function settingsBody\(\) \{.*?(?=function helpBody\(\) \{)', new_body + '\n\n', content, flags=re.DOTALL)

with open('frontend/js/main.js', 'w', encoding='utf-8') as f:
    f.write(content)
