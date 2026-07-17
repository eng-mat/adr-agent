// Light/dark theme, persisted. Applied via data-theme on <html>.
const KEY = "adr.theme";

export function getTheme() {
  return localStorage.getItem(KEY) || "dark";
}

export function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(KEY, theme);
}

export function initTheme() {
  applyTheme(getTheme());
}
