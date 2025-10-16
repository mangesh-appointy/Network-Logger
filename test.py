import maxEnv.ipynb.circle_area as circle_area
import time
import sys

print(f"test.py is run")

# Measure time and size for the call
start_time = time.time()
result = circle_area.calculate(5)  # Example call
elapsed_time = time.time() - start_time

# Get size of result
result_size = sys.getsizeof(result)

# Print time (in seconds) and size (in bytes) without headers
print(f"{elapsed_time:.6f}, {result_size}")