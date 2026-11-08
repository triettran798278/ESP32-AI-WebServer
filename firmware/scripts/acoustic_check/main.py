#!/usr/bin/env python3
"""
audio
Qt GUI + Matplotlib + UDPreceive + AFSK
"""

import sys
import asyncio
from graphic import main

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("user")
    except Exception as e:
        print(f": {e}")
        sys.exit(1)
