import re
from devin.assistant import replace_number_words

query = "write a mail to cu240251013@coeruniversity.ac.in for thanking him for his support in a ai project"
query_clean = re.sub(r'[^\w\s]', '', query)
query_clean = replace_number_words(query_clean)

crypto_kw = ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'dogecoin', 'doge',
             'solana', 'sol', 'binance', 'bnb', 'ripple', 'xrp', 'cardano', 'ada',
             'litecoin', 'ltc', 'polkadot', 'polygon', 'matic', 'avalanche', 'avax',
             'chainlink', 'link', 'uniswap', 'uni']

# Old logic
print("Old logic triggers:", any(w in query_clean for w in crypto_kw))

# New logic
query_words = set(query_clean.split())
print("New logic triggers:", any(w in query_words for w in crypto_kw))
