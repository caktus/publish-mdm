---
name: flowbite
description: Flowbite UI component patterns for this Django/HTMX/Alpine.js project. Use when adding or modifying UI components to keep visual consistency. Components are vendor-bundled at config/static/js/vendor/flowbite.min.js (no CDN needed).
---

# Flowbite Components — Publish MDM Reference

Flowbite is a free, open-source UI component library built on Tailwind CSS. It provides
ready-to-use HTML components with `data-*` attributes and a small JS plugin for interactive
behaviour (modals, dropdowns, toggles, etc.). Full component reference: https://flowbite.com/docs/

This project uses Flowbite's **vendored JS** (`config/static/js/vendor/flowbite.min.js`) —
no CDN, no npm import needed. The instance manager is available globally as `window.FlowbiteInstances`.

## Available Components (full list)

**UI Components:** Accordion, Alert, Avatar, Badge, Banner, Bottom navigation, Breadcrumb,
Buttons, Button group, Card, Carousel, Chat bubble, Clipboard, Datepicker, Device mockups,
Drawer, Dropdown, Footer, Forms, Gallery, Indicators, Jumbotron, KBD, List group, Mega menu,
Modal, Navbar, Pagination, Popover, Progress, Rating, Sidebar, Skeleton, Speed dial, Spinner,
Stepper, Tables, Tabs, Timeline, Toast, Tooltip, Typography, Video

**Form components:** Input field, File input, Search input, Number input, Phone input, Select,
Textarea, Timepicker, Checkbox, Radio, **Toggle** (switch), Range, Floating label

**Plugins:** Charts, Datatables, WYSIWYG

**Resources:** Flowbite Icons (https://flowbite.com/icons/), Flowbite Figma

Component docs live at `https://flowbite.com/docs/components/<name>/` and
`https://flowbite.com/docs/forms/<name>/`.

## Project CSS Conventions

- **Primary color** — `primary-*` (maps to the Tailwind `primary` color alias, configured in `tailwind.config.js`)
- **Buttons** — use project utility classes: `btn btn-primary`, `btn btn-outline`, `btn btn-outline btn-primary`
- **Section cards** — `bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5`
- **Labels** — `text-sm font-medium text-gray-900 dark:text-white`
- **Help text** — `text-sm text-gray-500 dark:text-gray-400`

---

## Toggle Switch (Checkbox)

Replace plain checkboxes with Flowbite toggle switches for binary options.

```html
<label class="inline-flex items-center gap-3 cursor-pointer"
       for="id_field_name">
    <input type="checkbox"
           name="field_name"
           id="id_field_name"
           {% if value %}checked{% endif %}
           class="sr-only peer">
    <div class="relative w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2
                peer-focus:ring-primary-300 dark:peer-focus:ring-primary-800 rounded-full peer
                dark:bg-gray-700 peer-checked:after:translate-x-full
                rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white
                after:content-[''] after:absolute after:top-[2px] after:start-[2px]
                after:bg-white after:border-gray-300 after:border after:rounded-full
                after:h-4 after:w-4 after:transition-all dark:border-gray-600
                peer-checked:bg-blue-600 dark:peer-checked:bg-blue-600">
    </div>
    <span class="text-sm font-medium text-gray-900 dark:text-white">Label text</span>
</label>
```

> **IMPORTANT**: The `sr-only peer` input is visually hidden but a sibling `<div>` captures pointer events. Playwright's `check` command cannot click sr-only inputs when a div is in the way. Use JS instead:
> ```bash
> playwright-cli eval "document.querySelector('label:has(input[name=\"field_name\"])').click()"
> ```

### Django form field rendering

When rendering from a Django form field, use these template variables:

```html
<label class="inline-flex items-center gap-3 cursor-pointer"
       for="{{ form.my_bool_field.id_for_label }}">
    <input type="checkbox"
           name="{{ form.my_bool_field.html_name }}"
           id="{{ form.my_bool_field.id_for_label }}"
           {% if form.my_bool_field.value %}checked{% endif %}
           class="sr-only peer">
    <div class="relative w-9 h-5 ...peer-checked:bg-blue-600..."></div>
    <span class="text-sm ...">{{ form.my_bool_field.label }}</span>
</label>
{{ form.my_bool_field.errors }}
```

---

## Modal

Modals use HTML `data-*` attributes — no JavaScript required for basic open/close.

```html
<!-- Trigger button -->
<button type="button"
        data-modal-target="my-modal"
        data-modal-toggle="my-modal"
        class="btn btn-outline btn-primary">
    Open Modal
</button>

<!-- Modal -->
<div id="my-modal"
     tabindex="-1"
     aria-hidden="true"
     class="hidden overflow-y-auto overflow-x-hidden fixed top-0 right-0 left-0 z-50
            justify-center items-center w-full md:inset-0 h-[calc(100%-1rem)] max-h-full">
    <div class="relative p-4 w-full max-w-2xl max-h-full">
        <div class="relative bg-white rounded-lg shadow dark:bg-gray-700">
            <!-- Header -->
            <div class="flex items-center justify-between p-4 border-b dark:border-gray-600 rounded-t">
                <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
                    Modal Title
                </h3>
                <button type="button"
                        data-modal-hide="my-modal"
                        class="text-gray-400 bg-transparent hover:bg-gray-200 hover:text-gray-900
                               rounded-lg text-sm w-8 h-8 ms-auto inline-flex justify-center
                               items-center dark:hover:bg-gray-600 dark:hover:text-white">
                    <svg class="w-3 h-3" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"
                         fill="none" viewBox="0 0 14 14">
                        <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"
                              stroke-width="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6"/>
                    </svg>
                    <span class="sr-only">Close modal</span>
                </button>
            </div>
            <!-- Body -->
            <div class="p-4">
                <p class="text-gray-600 dark:text-gray-400">Modal body content here.</p>
            </div>
            <!-- Footer (optional) -->
            <div class="flex items-center p-4 border-t dark:border-gray-600 rounded-b gap-3">
                <button type="button" class="btn btn-primary">Save</button>
                <button type="button" data-modal-hide="my-modal" class="btn btn-outline">Cancel</button>
            </div>
        </div>
    </div>
</div>
```

### Closing a modal programmatically (e.g., after HTMX save)

HTML normalizes attribute names to lowercase, so `hx-on:htmx:afterRequest` doesn't work reliably (the event is `htmx:afterRequest` with capital R). Use an inline `<script>` in the HTMX response instead:

```html
{% if saved %}
<script>
    (function () {
        var m = window.FlowbiteInstances && window.FlowbiteInstances.getInstance("Modal", "my-modal");
        if (m) m.hide();
    })();
</script>
{% endif %}
```

HTMX executes `<script>` tags in swapped content, so this runs after a successful save.

### FlowbiteInstances API

```javascript
// Get an instance (instances stored in FlowbiteInstances._instances, not .instances)
const modal = FlowbiteInstances.getInstance('Modal', 'modal-id');
modal.show();
modal.hide();
modal.toggle();
```

---

## Badge / Pill

Use for status indicators and scope labels.

```html
<!-- Blue (informational / org) -->
<span class="inline-flex items-center bg-blue-100 text-blue-700 text-xs font-medium
             px-2 py-0.5 rounded-full dark:bg-blue-900 dark:text-blue-300">
    Org
</span>

<!-- Purple (fleet) -->
<span class="inline-flex items-center bg-purple-100 text-purple-700 text-xs font-medium
             px-2 py-0.5 rounded-full dark:bg-purple-900 dark:text-purple-300">
    Fleet
</span>

<!-- Green (success/configured) -->
<span class="inline-flex items-center bg-green-100 text-green-700 text-xs font-medium
             px-2 py-0.5 rounded-full dark:bg-green-900 dark:text-green-300">
    Configured
</span>

<!-- Gray (neutral) -->
<span class="inline-flex items-center bg-gray-100 text-gray-600 text-xs font-medium
             px-2 py-0.5 rounded-full dark:bg-gray-700 dark:text-gray-300">
    Label
</span>
```

---

## Tables

Standard table used throughout the project:

```html
<div class="overflow-x-auto">
    <table class="w-full text-sm text-left text-gray-500 dark:text-gray-400">
        <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700
                      dark:text-gray-400">
            <tr>
                <th scope="col" class="px-4 py-3">Column A</th>
                <th scope="col" class="px-4 py-3">Column B</th>
                <th scope="col" class="px-4 py-3">Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for item in items %}
                <tr class="border-b dark:border-gray-700">
                    <td class="px-4 py-3">{{ item.name }}</td>
                    <td class="px-4 py-3">{{ item.value }}</td>
                    <td class="px-4 py-3">
                        <button class="btn btn-outline btn-primary text-sm">Edit</button>
                    </td>
                </tr>
            {% empty %}
                <tr>
                    <td colspan="3" class="px-4 py-3 text-center text-gray-400">
                        No items yet.
                    </td>
                </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
```

---

## Form Inputs (Tailwind/Flowbite style)

### Text input

```html
<div>
    <label class="block text-sm font-medium text-gray-900 dark:text-white mb-1"
           for="id_field">Field label</label>
    <input type="text"
           name="field"
           id="id_field"
           value="{{ value }}"
           class="border rounded-md block w-full text-sm bg-gray-50 border-gray-300
                  text-gray-900 p-2.5 focus:ring-primary-500 focus:border-primary-500
                  dark:bg-gray-700 dark:border-gray-600 dark:text-white"
           placeholder="Placeholder text">
    <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">Help text.</p>
</div>
```

### Select dropdown

```html
<div>
    <label class="block text-sm font-medium text-gray-900 dark:text-white mb-1"
           for="id_field">Label</label>
    <select name="field" id="id_field"
            class="border rounded-md block w-full text-sm bg-gray-50 border-gray-300
                   text-gray-900 p-2.5 focus:ring-primary-500 focus:border-primary-500
                   dark:bg-gray-700 dark:border-gray-600 dark:text-white">
        <option value="">---------</option>
        <option value="val1">Option 1</option>
    </select>
</div>
```

> **Note**: When using Django form fields with `PlatformFormMixin`, the `{{ form.field }}` widget renders with these classes automatically. For manually rendered toggles or custom layouts, use the patterns above.

---

## Section Card Layout

All policy editor sections use this card pattern:

```html
<div class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200
            dark:border-gray-700 p-5">
    <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-1">
        Section Title
    </h3>
    <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">
        Brief description of this section.
    </p>
    <!-- content / forms -->
</div>
```

---

## Auto-Save Pattern (HTMX + Alpine.js)

All policy editor forms use auto-save on change with a hidden submit button for Enter key support:

```html
<form hx-post="{% url 'publish_mdm:policy-save-section' request.organization.slug policy.pk %}"
      hx-target="#section-id"
      hx-swap="innerHTML"
      hx-trigger="change, submit">
    {% csrf_token %}
    <!-- form fields -->
    <button type="submit" class="sr-only" tabindex="-1">Save</button>
</form>
{% if saved %}
    <span x-data="{ vis: true }"
          x-init="setTimeout(() => { vis = false }, 2500)"
          x-show="vis"
          x-transition:leave="transition-opacity duration-500"
          x-transition:leave-start="opacity-100"
          x-transition:leave-end="opacity-0"
          class="mt-3 block text-sm text-green-600 dark:text-green-400">✓ Saved</span>
{% endif %}
```

- `hx-trigger="change, submit"` — fires on field change or form submit (Enter key)
- `hx-target="#section-id"` — replaces the section's inner content, preserving the outer `id` for future swaps
- `hx-swap="innerHTML"` — **always use innerHTML, not outerHTML**, to preserve the target element's ID

---

## CSS Flash Animation (Save Indicator for Table Rows)

For in-table auto-save feedback (e.g., app rows) where there's no space for text, a row highlight fade is used instead:

```css
/* In tailwind-entry.css */
@keyframes save-flash {
    0%   { background-color: rgb(187 247 208 / 0.6); }
    100% { background-color: transparent; }
}
.save-flash { animation: save-flash 2s ease-out forwards; }
```

```html
<!-- In the form that auto-saves inside a <tr> -->
<span x-data="{}"
      x-init="const tr = $el.closest('tr');
              tr.classList.remove('save-flash');
              void tr.offsetWidth;
              tr.classList.add('save-flash')">
</span>
```

`void tr.offsetWidth` forces a DOM reflow so the animation restarts even if triggered twice quickly.

---

## Clipboard Copy Button

```html
<button type="button"
        title="Copy to clipboard"
        data-copy="{{ value_to_copy }}"
        onclick="navigator.clipboard.writeText(this.dataset.copy).catch(()=>{})"
        class="text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 ml-1
               focus:outline-none transition-colors">
    <svg class="w-4 h-4" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"
         fill="none" viewBox="0 0 18 20">
        <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"
              stroke-width="2"
              d="M12 2h4a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h4m6 0a1 1 0 0 0-1-1H7a1 1 0 0 0-1 1m6 0H6m1 5h6M7 11h6M7 15h4"/>
    </svg>
    <span class="sr-only">Copy</span>
</button>
```

For Django template variables: use `{% templatetag openvariable %}` and `{% templatetag closevariable %}` to render `{{` and `}}` as literal characters in `data-copy`:

```html
data-copy="{% templatetag openvariable %} {{ var.key }} {% templatetag closevariable %}"
```

---

## Alpine.js Patterns

Alpine.js (`x-data`, `x-show`, `x-init`, `x-transition`) is vendored at `config/static/js/vendor/alpine.min.js`.

### Conditional field visibility

```html
<form x-data="{ scope: '{{ form.scope.value }}' }">
    <select name="{{ form.scope.html_name }}"
            @change="scope = $event.target.value">
        {{ form.scope }}
    </select>
    <div x-show="scope === 'fleet'">
        <!-- fleet-only field -->
    </div>
</form>
```

### Fade-out notification

```html
<span x-data="{ vis: true }"
      x-init="setTimeout(() => { vis = false }, 2500)"
      x-show="vis"
      x-transition:leave="transition-opacity duration-500"
      x-transition:leave-start="opacity-100"
      x-transition:leave-end="opacity-0"
      class="text-sm text-green-600 dark:text-green-400">
    ✓ Saved
</span>
```

---

## HTMX OOB (Out-of-Band) Swaps

Use to update elements outside the main `hx-target` in a single response:

```html
<!-- In the HTMX response, alongside the main content: -->
<span id="page-title-heading" hx-swap-oob="true">New Title</span>
```

The element with `hx-swap-oob="true"` must match an `id` on the page. HTMX updates both the target and all OOB elements in the same response.

---

## Key HTMX Notes for This Project

- **Event names are camelCase**: HTMX fires `htmx:afterRequest`, `htmx:afterSwap`, etc. (camelCase).
- **HTML lowercases attribute names**: `hx-on:htmx:afterRequest` becomes `hx-on:htmx:afterrequest` in the DOM, which never matches. Use inline `<script>` tags instead.
- **`hx-swap="innerHTML"` vs `outerHTML`**: Use `innerHTML` to preserve the target element's `id`. `outerHTML` removes the element, breaking future OOB swaps targeting that id.
- **HTMX executes scripts**: `<script>` tags in HTMX-swapped content are executed.

---

## Tailwind CSS Rebuild

After adding new CSS classes to templates that weren't previously in the build:

```bash
# Sandbox:
.npm-sandbox/node_modules/.bin/tailwindcss \
  -i config/assets/styles/tailwind-entry.css \
  -o config/static/css/main.css --minify

# Host (macOS):
node_modules/.bin/tailwindcss \
  -i config/assets/styles/tailwind-entry.css \
  -o config/static/css/main.css --minify
```

`config/static/css/main.css` is in `.gitignore` — it gets rebuilt on deploy.
