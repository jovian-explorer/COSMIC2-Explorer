import re
with open('frontend/js/main.js', 'r', encoding='utf-8') as f:
    content = f.read()

help_body_new = """function helpBody() {
  const container = el('div', {class: 'stack'});
  container.innerHTML = '<p>Loading guidebook...</p>';
  fetch('/help.html')
    .then(r => r.text())
    .then(html => {
      container.innerHTML = html;
    })
    .catch(err => {
      container.innerHTML = `<p class="error">Failed to load help: ${err}</p>`;
    });
  return container;
}"""

content = re.sub(r'function helpBody\(\) \{.*?(?=function aboutBody\(\) \{)', help_body_new + '\n\n', content, flags=re.DOTALL)

with open('frontend/js/main.js', 'w', encoding='utf-8') as f:
    f.write(content)
