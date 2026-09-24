import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost/test")

from retrieval import retrieve_relevant_chunks


class RecordingSession:
    def execute(self, query, parameters):
        self.query = str(query)
        self.parameters = parameters
        return []


class TenantRetrievalTests(unittest.TestCase):
    def test_tenant_is_bound_into_retrieval_query(self):
        session = RecordingSession()

        results = retrieve_relevant_chunks(
            session=session,
            query_vector=[0.0] * 384,
            tenant_id="tenant-alpha",
        )

        self.assertEqual(results, [])
        self.assertIn("d.tenant_id = :tenant_id", session.query)
        self.assertEqual(session.parameters["tenant_id"], "tenant-alpha")


if __name__ == "__main__":
    unittest.main()
