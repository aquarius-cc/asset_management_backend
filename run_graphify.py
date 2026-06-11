import json
import sys
from pathlib import Path
from graphify.detect import detect

def main():
    result = detect(Path('.'))
    print('Detected files:')
    print('  Total:', result.get('total_files', 0), 'files, ~', result.get('total_words', 0), 'words')
    for file_type, files in result.get('files', {}).items():
        if files:
            print('  ', file_type, ':', len(files), 'files')

    with open('.graphify_detect.json', 'w') as f:
        json.dump(result, f, indent=2)

    print('Detection complete.')

if __name__ == '__main__':
    main()
