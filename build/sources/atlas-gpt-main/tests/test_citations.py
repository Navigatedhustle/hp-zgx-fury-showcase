from atlas.documents import citation_check

def fixture():
    p={'id':'doc:0','text':'Synthetic Q4 memo. Revenue is $724,300,000. Margin is 57%.'}
    d={'id':'doc','title':'Board memo','passages':[p]}
    c={'document_id':'doc','document':'Board memo','passage_id':'doc:0','passage':p['text']}
    return {'documents':[d]},c

def test_citations_require_real_id_exact_passage_and_numbers():
    index,c=fixture()
    assert citation_check(c['passage'],[c],index)['passed']
    assert not citation_check(c['passage']+' Profit is $999,999,999.',[c],index)['passed']
    assert not citation_check(c['passage'],[{**c,'passage_id':'missing'}],index)['passed']
    assert not citation_check('Revenue is $999.',[{**c,'passage':'Revenue is $999.'}],index)['passed']
    assert not citation_check(c['passage']+' FY28 outlook.',[c],index)['passed']
