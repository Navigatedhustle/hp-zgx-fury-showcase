"""The browser UI is served by api.py; engine.py retains the tested transport."""
if __name__=='__main__':
    import uvicorn
    uvicorn.run('api:app',host='127.0.0.1',port=8501)
