"""Standard-library runner usable with Python isolated mode and no installation."""
import pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from graftline.__main__ import main
sys.exit(main())
