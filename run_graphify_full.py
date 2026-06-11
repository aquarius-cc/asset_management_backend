import json
import sys
from pathlib import Path

def step1_detect():
    print('=== Step 1: Detecting files ===')
    from graphify.detect import detect
    result = detect(Path('.'))
    print('  Total:', result.get('total_files', 0), 'files, ~', result.get('total_words', 0), 'words')
    for file_type, files in result.get('files', {}).items():
        if files:
            print('  ', file_type, ':', len(files), 'files')
    with open('.graphify_detect.json', 'w') as f:
        json.dump(result, f, indent=2)
    return result

def step2_ast_extraction(detect_result):
    print('\n=== Step 2: AST extraction ===')
    from graphify.extract import collect_files, extract
    
    code_files = []
    for f in detect_result.get('files', {}).get('code', []):
        code_files.extend(collect_files(Path(f)) if Path(f).is_dir() else [Path(f)])
    
    if code_files:
        print('  Processing', len(code_files), 'code files...')
        result = extract(code_files)
        print('  AST:', len(result['nodes']), 'nodes,', len(result['edges']), 'edges')
        with open('.graphify_ast.json', 'w') as f:
            json.dump(result, f, indent=2)
    else:
        print('  No code files - skipping AST extraction')
        with open('.graphify_ast.json', 'w') as f:
            json.dump({'nodes':[],'edges':[],'input_tokens':0,'output_tokens':0}, f)

def step3_merge():
    print('\n=== Step 3: Prepare merged extraction ===')
    
    with open('.graphify_ast.json', 'r') as f:
        ast = json.load(f)
    
    merged_final = {
        'nodes': ast['nodes'],
        'edges': ast['edges'],
        'hyperedges': [],
        'input_tokens': ast.get('input_tokens', 0),
        'output_tokens': ast.get('output_tokens', 0),
    }
    
    with open('.graphify_extract.json', 'w') as f:
        json.dump(merged_final, f, indent=2)
    
    print(f'  Merged: {len(merged_final["nodes"])} nodes, {len(merged_final["edges"])} edges')

def step4_build_and_cluster():
    print('\n=== Step 4: Build graph and cluster ===')
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.report import generate
    from graphify.export import to_json
    
    with open('.graphify_extract.json', 'r') as f:
        extraction = json.load(f)
    
    with open('.graphify_detect.json', 'r') as f:
        detection = json.load(f)
    
    G = build_from_json(extraction)
    print(f'  Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges')
    
    communities = cluster(G)
    print(f'  Clustered into {len(communities)} communities')
    
    cohesion = score_all(G, communities)
    
    tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: 'Community ' + str(cid) for cid in communities}
    questions = suggest_questions(G, communities, labels)
    
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, '.', suggested_questions=questions)
    Path('graphify-out/GRAPH_REPORT.md').write_text(report)
    print('  Report generated: graphify-out/GRAPH_REPORT.md')
    
    to_json(G, communities, 'graphify-out/graph.json')
    print('  Graph JSON exported: graphify-out/graph.json')
    
    analysis = {
        'communities': {str(k): v for k, v in communities.items()},
        'cohesion': {str(k): v for k, v in cohesion.items()},
        'gods': gods,
        'surprises': surprises,
        'questions': questions,
    }
    with open('.graphify_analysis.json', 'w') as f:
        json.dump(analysis, f, indent=2)
    
    print('  Top God nodes:')
    for g in gods[:10]:
        print(f'    - {g["label"]}')
    print('  Suggested questions:', len(questions))

def step5_generate_html():
    print('\n=== Step 5: Generate HTML visualization ===')
    from graphify.build import build_from_json
    from graphify.export import to_html
    
    with open('.graphify_extract.json', 'r') as f:
        extraction = json.load(f)
    
    with open('.graphify_analysis.json', 'r') as f:
        analysis = json.load(f)
    
    G = build_from_json(extraction)
    
    if G.number_of_nodes() > 5000:
        print(f'  Graph has {G.number_of_nodes()} nodes - too large for HTML viz')
    else:
        communities = {int(k): v for k, v in analysis['communities'].items()}
        labels = {int(k): v for k, v in analysis.get('labels', {}).items()}
        
        to_html(G, communities, 'graphify-out/graph.html', community_labels=labels or None)
        print('  HTML visualization generated: graphify-out/graph.html')

def main():
    try:
        detect_result = step1_detect()
        step2_ast_extraction(detect_result)
        step3_merge()
        step4_build_and_cluster()
        step5_generate_html()
        
        print('\n=== Analysis complete ===')
        print('Outputs in graphify-out/:')
        print('  - graph.html          - interactive graph visualization')
        print('  - GRAPH_REPORT.md     - audit report')
        print('  - graph.json          - raw graph data')
        
    except Exception as e:
        print(f'Error during graphify analysis: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
