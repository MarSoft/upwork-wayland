{ pkgs ? import <nixpkgs> {} }:
with pkgs; mkShell {
  nativeBuildInputs = with pkgs; [
    gcc
    glib.dev
    gdk-pixbuf.dev
    xorg.libX11.dev
    pkg-config
  ];
}
