from google.cloud import firestore

# IMPORTANT: Hardcoded Project ID (required for Agent Platform compatibility)
PROJECT_ID = "qwiklabs-gcp-01-cb4e8877ebdc"

def seed_database():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection("destinations")

    seed_items = [
        {
            "id": "dest_kyoto",
            "name": "Fushimi Inari & Arashiyama Bamboo Grove",
            "city": "Kyoto",
            "country": "Japan",
            "category": "Culture & Nature",
            "description": "Historic shrines with thousands of vermilion torii gates and serene bamboo paths.",
            "price_range": "$$",
            "rating": 4.9
        },
        {
            "id": "dest_paris",
            "name": "Eiffel Tower & Seine River Cruise",
            "city": "Paris",
            "country": "France",
            "category": "Sightseeing & Romance",
            "description": "Iconic iron lattice tower with panoramic views and scenic evening river cruises.",
            "price_range": "$$$",
            "rating": 4.8
        },
        {
            "id": "dest_nyc",
            "name": "Central Park & Broadway Theater District",
            "city": "New York",
            "country": "USA",
            "category": "Entertainment & Parks",
            "description": "Sprawling urban park surrounded by world-class musical theater and dining.",
            "price_range": "$$$",
            "rating": 4.7
        },
        {
            "id": "dest_tokyo",
            "name": "Shinjuku & Shibuya Crossing Experience",
            "city": "Tokyo",
            "country": "Japan",
            "category": "City Life & Shopping",
            "description": "Vibrant neon lights, famous scrambled intersection, and endless culinary options.",
            "price_range": "$$",
            "rating": 4.9
        },
        {
            "id": "dest_barcelona",
            "name": "Basílica de la Sagrada Família & Park Güell",
            "city": "Barcelona",
            "country": "Spain",
            "category": "Architecture & Arts",
            "description": "Antoni Gaudí's masterpiece church and colorful mosaic gardens overlooking the sea.",
            "price_range": "$$",
            "rating": 4.85
        }
    ]

    for item in seed_items:
        doc_ref = collection_ref.document(item["id"])
        doc_ref.set(item)
        print(f"  ✓ Seeded destination: {item['name']} ({item['city']}, {item['country']})")

    print("Firestore database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
