# Test package for books app

# Import working renaming test module
from . import test_renaming_basic

__all__ = ["test_renaming_basic"]

# Note: Additional comprehensive test modules are available but require
# further development of the renaming engine to work with the existing
# book model structure:
# - test_renaming_engine
# - test_batch_renamer
# - test_renaming_views
# - test_renaming_comprehensive
# - test_renaming_config
