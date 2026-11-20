import {el} from './dom.mjs?v=20261120ar';
import {icon} from './icons.mjs?v=20261120ar';

export const MODEL_IDS = ['default', 'deepseek-flash', 'deepseek-v4-pro'];

export function modelLabel(id, defaultLabel = 'Provider default') {
  if (id === 'default') return defaultLabel;
  if (id === 'deepseek-flash') return 'DeepSeek Flash';
  if (id === 'deepseek-v4-pro') return 'DeepSeek V4 Pro';
  return id;
}

/** Modern radio-card picker used by the model dialog and the settings panel. */
export function modelPicker({value = 'default', defaultLabel, ariaLabel = '', onChange = () => {}}) {
  const group = el('div', {class: 'model-picker', role: 'radiogroup', 'aria-label': ariaLabel});
  const buttons = MODEL_IDS.map(id => {
    const check = icon('check', 17);
    check.classList.add('model-option-check');
    const button = el('button', {type: 'button', class: 'model-option', role: 'radio',
      'aria-checked': String(id === value)},
    el('span', {class: 'model-option-body'},
      el('span', {class: 'model-option-title'}, modelLabel(id, defaultLabel)),
      id === 'default' ? null : el('span', {class: 'model-option-id'}, id)),
    check);
    button.addEventListener('click', () => {
      for (const other of buttons) other.setAttribute('aria-checked', String(other === button));
      onChange(id);
    });
    group.append(button);
    return button;
  });
  return group;
}
