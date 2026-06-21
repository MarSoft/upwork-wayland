{ pkgs ? import <nixpkgs> {} }:
with pkgs; mkShell {
  nativeBuildInputs = with pkgs; [
    gcc
    glib.dev
    gdk-pixbuf.dev
    libx11.dev
    libxscrnsaver
    libxcb.dev
    pkg-config
  ];
}
