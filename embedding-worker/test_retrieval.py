import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv;
from processor import embedding_model
from retrieval import retrieve_relevant_chunks

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/lexguard")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def run_retrieval_test():
    query_string = "What is the limitation of liability in this contract?"
    print(f"Generating vector for query: '{query_string}'...\n")
    
    query_vector = embedding_model.encode(query_string).tolist()
    
    with SessionLocal() as session:
        print("Executing vector similarity search against PostgreSQL...")
        
        results = retrieve_relevant_chunks(
            session=session,
            query_vector=query_vector,
            top_k=3,
            distance_threshold=1.9
        )
        
        print(f"\nRetrieved {len(results)} relevant chunks below the 0.5 distance threshold:\n")
        print("=" * 60)
        
        for index, result in enumerate(results, start=1):
            print(f"--- Result {index} ---")
            print(f"Distance:    {result.distance:.4f}")
            print(f"Page Number: {result.page_number}")
            print(f"Content:\n{result.content.strip()}\n")
            print("=" * 60)

if __name__ == "__main__":
    run_retrieval_test()