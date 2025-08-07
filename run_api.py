import uvicorn

def main():
    """Run the Uvicorn server with reload enabled."""
    uvicorn.run("api:app", host="0.0.0.0", port=8080, reload=True)

if __name__ == "__main__":
    main()