import {motionReduced as reduced} from './settings-preferences.mjs?v=20261125c';
import './settings-preferences.mjs?v=20261125c';

/** True when the user asked for reduced motion (system or settings override). */
export function motionReduced() {
  return reduced();
}
