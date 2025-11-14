#!/usr/bin/env python
"""Comprehensive Test Suite Runner - FIXED VERSION (Includes Subdirectories)

This is the corrected version of run_all_tests_comprehensive.py that includes
test files from all subdirectories (backtest/, integration/, marketing/, unit/)

The original version only looked at root directory files.
This version uses rglob() to find all test_*.py files recursively.
"""

import subprocess
import os
import sys
from datetime import datetime
from pathlib import Path
import json
import time

# Configuration
TESTS_DIR = Path("backend/tests")
OUTPUT_DIR = Path(".")
TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# Output files
LOG_FILE = OUTPUT_DIR / f"ALL_TEST_EXECUTION_COMPLETE_{TIMESTAMP}.log"
CSV_FILE = OUTPUT_DIR / f"ALL_TEST_RESULTS_COMPLETE_{TIMESTAMP}.csv"
SUMMARY_FILE = OUTPUT_DIR / f"TEST_SUMMARY_COMPLETE_{TIMESTAMP}.txt"
JSON_FILE = OUTPUT_DIR / f"TEST_RESULTS_COMPLETE_{TIMESTAMP}.json"

def get_test_files():
    """Get all test files recursively (FIXED: uses rglob instead of glob)"""
    # FIXED: This now includes subdirectories
    test_files = sorted([str(f.relative_to(TESTS_DIR)) for f in TESTS_DIR.rglob("test_*.py")])
    return test_files

def parse_pytest_output(output):
    """Parse pytest output to extract test statistics"""
    passed = failed = skipped = 0
    
    for line in output.split('\n'):
        if 'passed' in line:
            try:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'passed':
                        passed = int(parts[i-1])
                        break
            except:
                pass
        
        if 'failed' in line:
            try:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'failed':
                        failed = int(parts[i-1])
                        break
            except:
                pass
        
        if 'skipped' in line:
            try:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'skipped':
                        skipped = int(parts[i-1])
                        break
            except:
                pass
    
    return passed, failed, skipped

def run_tests():
    """Run all tests and collect metrics"""
    test_files = get_test_files()
    total_files = len(test_files)
    
    print("\n" + "="*80)
    print("STARTING COMPREHENSIVE TEST SUITE (INCLUDES ALL SUBDIRECTORIES)")
    print("="*80)
    print(f"Total test files found: {total_files}")
    print(f"Includes: Root + backtest/ + integration/ + marketing/ + unit/")
    print(f"Log: {LOG_FILE}")
    print(f"CSV: {CSV_FILE}")
    print("="*80 + "\n")
    
    # Initialize output files
    with open(LOG_FILE, 'w') as f:
        f.write(f"Test Execution Log - {TIMESTAMP}\n")
        f.write("="*80 + "\n")
        f.write(f"Total test files: {total_files}\n")
        f.write(f"Includes subdirectories: backtest/, integration/, marketing/, unit/\n")
        f.write("="*80 + "\n\n")
    
    with open(CSV_FILE, 'w') as f:
        f.write("TestFile,Total,Passed,Failed,Skipped,Duration,Status\n")
    
    # Statistics
    results = []
    total_stats = {
        'files': 0,
        'total_tests': 0,
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'total_time': 0
    }
    
    # Directory breakdown
    dir_stats = {}
    
    suite_start = time.time()
    
    for idx, test_file in enumerate(test_files, 1):
        percent = int((idx / total_files) * 100)
        status_line = f"[{idx}/{total_files} - {percent}%] {test_file}"
        
        print(status_line, end=" ... ", flush=True)
        
        test_path = TESTS_DIR / test_file
        test_start = time.time()
        
        try:
            # Run test
            result = subprocess.run(
                [".venv/Scripts/python.exe", "-m", "pytest", str(test_path), "-q", "--tb=no"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            test_duration = time.time() - test_start
            output = result.stdout + result.stderr
            
            # Parse results
            passed, failed, skipped = parse_pytest_output(output)
            total = passed + failed + skipped
            
            # Determine status
            if failed == 0 and total > 0:
                status = "PASS"
                color_code = "\033[92m"  # Green
            elif failed > 0:
                status = "FAIL"
                color_code = "\033[91m"  # Red
            else:
                status = "SKIP"
                color_code = "\033[93m"  # Yellow
            
            reset_code = "\033[0m"
            
            # Print result
            result_str = f"P:{passed} F:{failed} S:{skipped} ({test_duration:.1f}s)"
            print(f"{color_code}{status}{reset_code} | {result_str}")
            
            # Update totals
            total_stats['files'] += 1
            total_stats['total_tests'] += total
            total_stats['passed'] += passed
            total_stats['failed'] += failed
            total_stats['skipped'] += skipped
            total_stats['total_time'] += test_duration
            
            # Track by directory
            dir_name = test_file.split('/')[0] if '/' in test_file else 'root'
            if dir_name not in dir_stats:
                dir_stats[dir_name] = {'files': 0, 'tests': 0, 'passed': 0, 'failed': 0}
            dir_stats[dir_name]['files'] += 1
            dir_stats[dir_name]['tests'] += total
            dir_stats[dir_name]['passed'] += passed
            dir_stats[dir_name]['failed'] += failed
            
            # Store result
            result_obj = {
                'file': test_file,
                'total': total,
                'passed': passed,
                'failed': failed,
                'skipped': skipped,
                'duration': round(test_duration, 2),
                'status': status
            }
            results.append(result_obj)
            
            # Append to CSV
            with open(CSV_FILE, 'a') as f:
                f.write(f"{test_file},{total},{passed},{failed},{skipped},{round(test_duration, 2)},{status}\n")
            
            # Append to log
            with open(LOG_FILE, 'a') as f:
                f.write(f"[{idx}/{total_files}] {test_file}\n")
                f.write(f"  Passed: {passed}, Failed: {failed}, Skipped: {skipped}\n")
                f.write(f"  Duration: {test_duration:.2f}s, Status: {status}\n\n")
        
        except subprocess.TimeoutExpired:
            print(f"\033[91mTIMEOUT\033[0m (120s)")
            with open(LOG_FILE, 'a') as f:
                f.write(f"[{idx}/{total_files}] {test_file} - TIMEOUT\n\n")
            with open(CSV_FILE, 'a') as f:
                f.write(f"{test_file},0,0,0,0,120.00,TIMEOUT\n")
        
        except Exception as e:
            print(f"\033[91mERROR\033[0m: {str(e)[:50]}")
            with open(LOG_FILE, 'a') as f:
                f.write(f"[{idx}/{total_files}] {test_file} - ERROR: {str(e)}\n\n")
    
    suite_duration = time.time() - suite_start
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUITE COMPLETE")
    print("="*80)
    print(f"Total Files: {total_stats['files']}")
    print(f"Total Tests: {total_stats['total_tests']}")
    print(f"\033[92mPassed: {total_stats['passed']}\033[0m")
    print(f"\033[91mFailed: {total_stats['failed']}\033[0m")
    print(f"\033[93mSkipped: {total_stats['skipped']}\033[0m")
    print(f"Total Duration: {suite_duration/60:.2f} minutes")
    
    pass_rate = (total_stats['passed'] / total_stats['total_tests'] * 100) if total_stats['total_tests'] > 0 else 0
    print(f"Pass Rate: {pass_rate:.2f}%")
    print("="*80)
    
    # Print directory breakdown
    print("\nBREAKDOWN BY DIRECTORY:")
    print("="*80)
    for dir_name in sorted(dir_stats.keys()):
        stats = dir_stats[dir_name]
        dir_pass_rate = (stats['passed'] / stats['tests'] * 100) if stats['tests'] > 0 else 0
        print(f"{dir_name:20} | Files: {stats['files']:3} | Tests: {stats['tests']:4} | Passed: {stats['passed']:4} | Failed: {stats['failed']:3} | Pass Rate: {dir_pass_rate:6.2f}%")
    print("="*80 + "\n")
    
    # Generate summary file
    failed_results = [r for r in results if r['status'] == 'FAIL']
    failed_results.sort(key=lambda x: x['failed'], reverse=True)
    
    summary_text = f"""COMPREHENSIVE TEST SUITE SUMMARY (COMPLETE - ALL SUBDIRECTORIES)
Generated: {TIMESTAMP}
Total Duration: {suite_duration/60:.2f} minutes

OVERALL STATISTICS:
- Total Test Files: {total_stats['files']}
- Total Tests: {total_stats['total_tests']}
- Passed: {total_stats['passed']}
- Failed: {total_stats['failed']}
- Skipped: {total_stats['skipped']}
- Pass Rate: {pass_rate:.2f}%

DIRECTORY BREAKDOWN:
"""
    
    for dir_name in sorted(dir_stats.keys()):
        stats = dir_stats[dir_name]
        dir_pass_rate = (stats['passed'] / stats['tests'] * 100) if stats['tests'] > 0 else 0
        summary_text += f"\n{dir_name.upper()}:\n"
        summary_text += f"  Files: {stats['files']}, Tests: {stats['tests']}, Passed: {stats['passed']}, Failed: {stats['failed']}, Pass Rate: {dir_pass_rate:.2f}%\n"
    
    summary_text += f"\n\nFAILED TEST FILES ({len(failed_results)} files):\n"
    
    if failed_results:
        for res in failed_results:
            summary_text += f"\n{res['file']}: {res['failed']} failures\n"
    else:
        summary_text += "\nNone! All tests passed!\n"
    
    summary_text += "\n\nTOP PRIORITY FIXES (Most Failures First):\n"
    for res in failed_results[:15]:
        summary_text += f"  {res['file']}: {res['failed']} failures\n"
    
    with open(SUMMARY_FILE, 'w') as f:
        f.write(summary_text)
    
    # Save JSON
    with open(JSON_FILE, 'w') as f:
        json.dump({
            'timestamp': TIMESTAMP,
            'duration': suite_duration,
            'statistics': total_stats,
            'directory_breakdown': dir_stats,
            'results': results
        }, f, indent=2)
    
    print(f"Summary: {SUMMARY_FILE}")
    print(f"CSV: {CSV_FILE}")
    print(f"JSON: {JSON_FILE}")
    print(f"Log: {LOG_FILE}")

if __name__ == "__main__":
    try:
        run_tests()
    except KeyboardInterrupt:
        print("\n\nTest suite interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
