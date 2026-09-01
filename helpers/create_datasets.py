from dotenv import load_dotenv
from langsmith import Client

from agents.config import DATASET_NAME

# Not override=True: real environment variables must win over a local .env.
load_dotenv()

client = Client()

# Answers are checked against the Chinook snapshot get_engine_for_chinook_db()
# downloads, whose invoices run 2021-2025 and top out at $49.62 per customer.
examples = [
    {
        "inputs": {
            "question": "How many songs do you have by Queen?",
        },
        "outputs": {
            "sql": "SELECT COUNT(*) FROM Track t JOIN Album al ON t.AlbumId = al.AlbumId JOIN Artist a ON al.ArtistId = a.ArtistId WHERE a.Name = 'Queen'",
            "response": "We have 45 songs by Queen in our database.",
        },
    },
    {
        "inputs": {
            "question": "What are the top 5 most expensive tracks?",
        },
        "outputs": {
            "sql": "SELECT Name, UnitPrice FROM Track ORDER BY UnitPrice DESC LIMIT 5",
            "response": "The five most expensive tracks are all priced at $1.99, the highest unit price in the catalogue.",
        },
    },
    {
        "inputs": {
            "question": "How many albums does Led Zeppelin have?",
        },
        "outputs": {
            "sql": "SELECT COUNT(*) FROM Album a JOIN Artist ar ON a.ArtistId = ar.ArtistId WHERE ar.Name = 'Led Zeppelin'",
            "response": "Led Zeppelin has 14 albums in our database.",
        },
    },
    {
        "inputs": {
            "question": "What is the total revenue from sales in 2023?",
        },
        "outputs": {
            "sql": "SELECT SUM(Total) FROM Invoice WHERE strftime('%Y', InvoiceDate) = '2023'",
            "response": "The total revenue from sales in 2023 was $469.58.",
        },
    },
    {
        "inputs": {
            "question": "Which customers have spent more than $40?",
        },
        "outputs": {
            "sql": "SELECT c.FirstName, c.LastName, SUM(i.Total) as TotalSpent FROM Customer c JOIN Invoice i ON c.CustomerId = i.CustomerId GROUP BY c.CustomerId HAVING SUM(i.Total) > 40 ORDER BY TotalSpent DESC",
            "response": "14 customers have spent more than $40, led by Helena Holy at $49.62, Richard Cunningham at $47.62 and Luis Rojas at $46.62.",
        },
    },
]

dataset_name = DATASET_NAME

if not client.has_dataset(dataset_name=dataset_name):
    dataset = client.create_dataset(dataset_name=dataset_name)
    client.create_examples(dataset_id=dataset.id, examples=examples)
