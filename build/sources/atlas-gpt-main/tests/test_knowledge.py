from atlas.data.upgrade import ensure
from atlas.knowledge import graph,provenance,record_id
from atlas.analytics import execute,rows

def test_graph_counts_records_and_real_edges():
    ensure()
    for persona in ['enterprise','university']:
        g=graph(persona);ids={n['id'] for n in g['nodes']}
        assert g['counts']['nodes']==len(ids)==sum(g['counts']['node_types'].values())
        assert g['counts']['edges']==len(g['edges'])
        assert all(e['source'] in ids and e['target'] in ids for e in g['edges'])
        for table,count in g['data']['tables'].items():
            expected=rows('SELECT COUNT(*) AS n FROM '+table+(' WHERE persona=?' if table=='sites' else ''),(persona,) if table=='sites' else ())[0]['n']
            assert count==expected

def test_provenance_exact_sql_keys_and_persona_scope():
    output=provenance(execute('forecast_quarter'),'enterprise',{})
    actual={record_id('pipeline',r) for r in rows('SELECT * FROM pipeline WHERE snapshot=?',('2026-10-07',))}
    used=next(s for s in output['sources'] if s['table']=='pipeline')
    assert set(used['row_ids'])==actual and used['rows']==len(actual)
    assert set(output['provenance']['node_ids'])<={n['id'] for n in graph('enterprise')['nodes']}
    output=provenance(execute('score_sites',{'persona':'university'}),'university',{})
    assert all(i.startswith('sites:university:') for i in output['provenance']['row_ids'])
