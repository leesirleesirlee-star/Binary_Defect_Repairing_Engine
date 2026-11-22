/**
 * Console-side half of the welcome shield-scan transition. Loaded before the
 * conversation app so the arrival veil covers the first paint.
 */
import {arrive} from './warp.mjs?v=20261121y';

arrive();
