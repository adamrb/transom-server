/**
 * Material Symbols Rounded, weight 400, one import per glyph so only the icons we use ship.
 * Each file is `<svg viewBox="0 -960 960 960"><path d="…"/></svg>`; we keep the path data and
 * draw it ourselves so the glyph takes `currentColor` and any size.
 *
 * To add an icon: add a line here (the file name is the Material Symbols name) and it becomes a
 * valid `IconName` everywhere. Filled variants live at `…/rounded/<name>-fill.svg`.
 */
import add from '@material-symbols/svg-400/rounded/add.svg?raw';
import android from '@material-symbols/svg-400/rounded/android.svg?raw';
import arrow_back from '@material-symbols/svg-400/rounded/arrow_back.svg?raw';
import block from '@material-symbols/svg-400/rounded/block.svg?raw';
import check from '@material-symbols/svg-400/rounded/check.svg?raw';
import check_circle from '@material-symbols/svg-400/rounded/check_circle.svg?raw';
import chevron_right from '@material-symbols/svg-400/rounded/chevron_right.svg?raw';
import close from '@material-symbols/svg-400/rounded/close.svg?raw';
import content_copy from '@material-symbols/svg-400/rounded/content_copy.svg?raw';
import contrast from '@material-symbols/svg-400/rounded/contrast.svg?raw';
import dark_mode from '@material-symbols/svg-400/rounded/dark_mode.svg?raw';
import delete_ from '@material-symbols/svg-400/rounded/delete.svg?raw';
import description from '@material-symbols/svg-400/rounded/description.svg?raw';
import devices from '@material-symbols/svg-400/rounded/devices.svg?raw';
import download from '@material-symbols/svg-400/rounded/download.svg?raw';
import edit from '@material-symbols/svg-400/rounded/edit.svg?raw';
import computer from '@material-symbols/svg-400/rounded/computer.svg?raw';
import error from '@material-symbols/svg-400/rounded/error.svg?raw';
import folder from '@material-symbols/svg-400/rounded/folder.svg?raw';
import format_list_bulleted from '@material-symbols/svg-400/rounded/format_list_bulleted.svg?raw';
import forward_10 from '@material-symbols/svg-400/rounded/forward_10.svg?raw';
import forward_30 from '@material-symbols/svg-400/rounded/forward_30.svg?raw';
import graphic_eq from '@material-symbols/svg-400/rounded/graphic_eq.svg?raw';
import group from '@material-symbols/svg-400/rounded/group.svg?raw';
import history from '@material-symbols/svg-400/rounded/history.svg?raw';
import ios_share from '@material-symbols/svg-400/rounded/ios_share.svg?raw';
import keyboard_arrow_down from '@material-symbols/svg-400/rounded/keyboard_arrow_down.svg?raw';
import keyboard_arrow_up from '@material-symbols/svg-400/rounded/keyboard_arrow_up.svg?raw';
import light_mode from '@material-symbols/svg-400/rounded/light_mode.svg?raw';
import link from '@material-symbols/svg-400/rounded/link.svg?raw';
import logout from '@material-symbols/svg-400/rounded/logout.svg?raw';
import mic from '@material-symbols/svg-400/rounded/mic.svg?raw';
import mobile from '@material-symbols/svg-400/rounded/mobile.svg?raw';
import more_vert from '@material-symbols/svg-400/rounded/more_vert.svg?raw';
import open_in_new from '@material-symbols/svg-400/rounded/open_in_new.svg?raw';
import palette from '@material-symbols/svg-400/rounded/palette.svg?raw';
import pause from '@material-symbols/svg-400/rounded/pause.svg?raw';
import person from '@material-symbols/svg-400/rounded/person.svg?raw';
import play_arrow from '@material-symbols/svg-400/rounded/play_arrow.svg?raw';
import qr_code from '@material-symbols/svg-400/rounded/qr_code.svg?raw';
import refresh from '@material-symbols/svg-400/rounded/refresh.svg?raw';
import replay from '@material-symbols/svg-400/rounded/replay.svg?raw';
import replay_10 from '@material-symbols/svg-400/rounded/replay_10.svg?raw';
import replay_30 from '@material-symbols/svg-400/rounded/replay_30.svg?raw';
import schedule from '@material-symbols/svg-400/rounded/schedule.svg?raw';
import search from '@material-symbols/svg-400/rounded/search.svg?raw';
import send from '@material-symbols/svg-400/rounded/send.svg?raw';
import settings from '@material-symbols/svg-400/rounded/settings.svg?raw';
import spellcheck from '@material-symbols/svg-400/rounded/spellcheck.svg?raw';
import star from '@material-symbols/svg-400/rounded/star.svg?raw';
import star_fill from '@material-symbols/svg-400/rounded/star-fill.svg?raw';
import tune from '@material-symbols/svg-400/rounded/tune.svg?raw';
import upload from '@material-symbols/svg-400/rounded/upload.svg?raw';
import visibility from '@material-symbols/svg-400/rounded/visibility.svg?raw';
import visibility_off from '@material-symbols/svg-400/rounded/visibility_off.svg?raw';
import volume_off from '@material-symbols/svg-400/rounded/volume_off.svg?raw';
import wand_stars from '@material-symbols/svg-400/rounded/wand_stars.svg?raw';
import warning from '@material-symbols/svg-400/rounded/warning.svg?raw';
import webhook from '@material-symbols/svg-400/rounded/webhook.svg?raw';

const RAW = {
  add,
  android,
  arrow_back,
  block,
  check,
  check_circle,
  chevron_right,
  close,
  /** the laptop glyph (Material renamed `laptop` to `computer`) */
  computer,
  content_copy,
  contrast,
  dark_mode,
  delete: delete_,
  description,
  devices,
  download,
  edit,
  error,
  folder,
  format_list_bulleted,
  forward_10,
  forward_30,
  graphic_eq,
  group,
  history,
  ios_share,
  /** expand / collapse chevrons (Material renamed `expand_more`/`expand_less`) */
  keyboard_arrow_down,
  keyboard_arrow_up,
  light_mode,
  link,
  logout,
  mic,
  /** the phone glyph (Material renamed `smartphone` to `mobile`) */
  mobile,
  more_vert,
  open_in_new,
  palette,
  pause,
  person,
  play_arrow,
  qr_code,
  refresh,
  replay,
  replay_10,
  replay_30,
  schedule,
  search,
  send,
  settings,
  spellcheck,
  star,
  star_fill,
  tune,
  upload,
  visibility,
  visibility_off,
  volume_off,
  /** the Automations glyph: three sparkles (Material renamed `auto_awesome` to `wand_stars`) */
  wand_stars,
  warning,
  webhook,
} as const;

export type IconName = keyof typeof RAW;
export const ICON_NAMES = Object.keys(RAW) as IconName[];

/** Material Symbols glyphs are drawn in a 960-unit box with the baseline at 0. */
export const ICON_VIEWBOX = '0 -960 960 960';

const cache = new Map<IconName, string>();

/** The `d` attribute(s) of a glyph, joined so one <path> draws it. */
export function iconPath(name: IconName): string {
  const hit = cache.get(name);
  if (hit !== undefined) return hit;
  const svg = RAW[name];
  const paths = [...svg.matchAll(/\sd="([^"]+)"/g)].map((m) => m[1]).join(' ');
  cache.set(name, paths);
  return paths;
}
