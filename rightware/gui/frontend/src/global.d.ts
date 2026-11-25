// The RIGHTWARE translator is installed globally so that declared string patches in pinned upstream modules can
// call it without adding imports to those modules (see overlay.manifest.json "strings").
declare global {
  // eslint-disable-next-line no-var
  var __rwT: (key: string) => string;
  // eslint-disable-next-line no-var
  var __rwSpeakable: (text: string) => string;
}
export {};
