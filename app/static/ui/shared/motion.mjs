import {motionReduced as reduced} from './settings-preferences.mjs?v=20261120ar';
import './settings-preferences.mjs?v=20261120ar';

/** True when the user asked for reduced motion (system or settings override). */
export function motionReduced() {
  return reduced();
}
