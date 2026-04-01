{ pkgs }:

{
  deps = [
    # Python
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.python311Packages.virtualenv

    # Node.js for Next.js dashboard
    pkgs.nodejs_20
    pkgs.nodePackages.npm

    # Android Debug Bridge
    pkgs.androidenv.androidPkgs_9_0.platform-tools

    # OpenCV system dependencies
    pkgs.libGL
    pkgs.libGLU
    pkgs.glib
    pkgs.gtk3
    pkgs.libSM
    pkgs.libXext
    pkgs.libXrender

    # Tesseract OCR
    pkgs.tesseract
    pkgs.tesseract4

    # Java (required for Appium)
    pkgs.jdk17

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
    TESSDATA_PREFIX = "${pkgs.tesseract4}/share/tessdata";
    JAVA_HOME = "${pkgs.jdk17}";
    LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.libGL
      pkgs.glib
      pkgs.libSM
      pkgs.libXext
      pkgs.libXrender
    ];
  };
}
