"""Small Korean keyword search; no model or external service is used."""
import re

STOPWORDS = {
    '알려주세요', '알려줘', '해주세요', '어떻게', '무엇인가요', '무슨', '뭐가',
    '방법', '사용', '제품', '있나요', '되나요', '인가요', '까요', '다른가요',
    '그럼', '그러면', '그건', '그것', '얼마나', '몇', '시간', '처음부터',
}
TOPICS = [
    (r'취침|수면', {'14', '15'}),
    (r'세탁|빨래|건조', {'21', '22'}),
    (r'리모컨|리모콘|페어링', {'10', '11'}),
    (r'배터리|건전지', {'10', '12', '28'}),
    (r'보증|환불|교환|무상수리', {'24', '25'}),
    (r'오류|에러|(?<![a-z0-9])e[1-3](?![a-z0-9])', {'23'}),
    (r'더블|양쪽|좌우|동일|똑같|온도|같게\s*맞', {'13', '20'}),
]


def query_terms(question):
    endings = ('이랑', '하고', '에서', '으로', '에게', '까지', '부터',
               '은', '는', '이', '가', '을', '를', '에', '와', '과', '도', '만', '요')
    terms = set()
    for word in re.findall(r'[가-힣]{2,}|[a-z0-9]+', question.lower()):
        if word in STOPWORDS:
            continue
        for ending in endings:
            if len(word) - len(ending) >= 2 and word.endswith(ending):
                word = word[:-len(ending)]
                break
        if len(word) >= 2 and word not in STOPWORDS:
            terms.add(word)
    return terms


def rank_pages(question, entries, limit=5):
    terms = query_terms(question)
    topic_pages = set()
    for pattern, pages in TOPICS:
        if re.search(pattern, question, re.IGNORECASE):
            topic_pages.update(pages)
    scored = []
    for entry in entries:
        title = entry['title'].lower()
        text = (title + ' ' + entry['summary']).lower()
        score = sum(3 if term in title else 1 for term in terms if term in text)
        if entry['page'] in topic_pages:
            score += 6
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda pair: (-pair[0], int(pair[1]['page'])))
    if not scored:
        return []
    threshold = max(1, scored[0][0] * 0.4)
    return [entry for score, entry in scored[:limit] if score >= threshold]


def contextual_question(question, messages, entries):
    """Reuse the last relevant user question only for short follow-up questions."""
    if rank_pages(question, entries):
        return question
    if len(question) <= 50 and re.search(r'그럼|그러면|그건|그것|몇\s*(시간|번|년|도)|얼마나', question):
        for message in reversed(messages):
            if message.get('role') == 'user' and rank_pages(message['content'], entries):
                return message['content'] + '\n추가 질문: ' + question
    return question
