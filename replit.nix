{ pkgs }:

{
  deps = [
    # Python
    pkgs.python311
    pkgs.python311Packages.pip

    # Node.js for Next.js dashboard
    pkgs.nodejs_20
    pkgs.nodePackages.npm

    # OpenCV system dependencies
    pkgs.libGL
    pkgs.glib

    # Tesseract OCR
    pkgs.tesseract

    # Build tools
    pkgs.gcc
    pkgs.gnumake
    pkgs.pkg-config

    # Utilities
    pkgs.curl
    pkgs.wget
    pkgs.git
    pkgs.unzip
  ];

  env = {
    PYTHONPATH = ".";
    LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.libGL
      pkgs.glib
    ];
  };
}
