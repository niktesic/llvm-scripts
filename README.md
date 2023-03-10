# llvm-scripts
Improved and new scripts for working with LLVM compiler infrastructure

## Scripts for testing debug-info preservation

### Improved script for conversion of debugify reports (JSON) into HTML

Script `llvm-original-di-preservation.py` from llvm-project/llvm/utils/ is improved to be resilient to large and bad formatted JSON reports.
Use command line option `-compress` to create highly compressed HTML reports.

Usage:
```
$  llvm-original-di-preserve.py -compress report.json report.html
```

### Script for automatic analysis of debug-info preservation in LLVM tests

New script `auto-debugify-tests.py` is created to detect debug-info losses in LLVM IR optimizations performed on tests from LLVM infrastructure.
Detection of debug-info losses is performed using `Debugify` passes in two modes - Sythethic (-debugify) and OriginalDebugInfo mode (verify-each-debuginfo-preserve).
Results (detected losses report) could be converted to HTML using `llvm-original-di-preservation.py`.

Usage (synthetic mode - default):
```
$ ./auto-debugify-tests.py -process-tests=TEST_DIR -use-lit=LIT_PATH -report-file=report.json
```

Usage (original-di mode):
```
$ ./auto-debugify-tests.py -mode=original -process-tests=TEST_DIR -use-lit=LIT_PATH -report-file=report.json
```
