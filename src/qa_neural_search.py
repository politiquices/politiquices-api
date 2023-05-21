from haystack.document_stores import ElasticsearchDocumentStore
from haystack.nodes import FARMReader, BM25Retriever
from haystack.pipelines import ExtractiveQAPipeline


class NeuralSearch:
    def __init__(self):
        self.host = "es_haystack"
        self.port = 9202

    @property
    def document_store(self):
        return ElasticsearchDocumentStore(host=self.host, port=self.port)

    @property
    def retriever(self):
        retriever = BM25Retriever(document_store=self.document_store)
        return retriever

    @property
    def reader(self):
        reader = FARMReader(model_name_or_path="deepset/roberta-base-squad2", use_gpu=False)
        return reader

    @property
    def pipeline(self):
        pipe = ExtractiveQAPipeline(self.reader, self.retriever)
        return pipe

    def predict(self, query):
        prediction = self.pipeline.run(
            query=query,
            params={"Retriever": {"top_k": 10}, "Reader": {"top_k": 5}},
        )
        return prediction


if __name__ == "__main__":
    haystack_db = NeuralSearch()
    answers = haystack_db.predict("Quem acusou José Sócrates?")
