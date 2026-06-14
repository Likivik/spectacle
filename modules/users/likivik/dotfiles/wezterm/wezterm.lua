local wezterm = require 'wezterm'
return {
  color_scheme = "dank-colors",
  keys = {
    { key = "c", mods = "CTRL", action = wezterm.action.CopyTo "ClipboardAndPrimarySelection" },
    { key = "v", mods = "CTRL", action = wezterm.action.PasteFrom "Clipboard" },
  },
}
