import streamlit as st
import os
import tempfile
import requests
from chunker import get_db, ingest_book
from normalize import build_prompt

st.set_page_config(page_title="📚 Библиотечный RAG", page_icon="📖", layout="wide")

# Инициализация
if "db" not in st.session_state:
    st.session_state.db = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "openrouter_key" not in st.session_state:
    st.session_state.openrouter_key = ""

# Боковая панель
with st.sidebar:
    st.title("⚙️ Управление")
    
    db_path = st.text_input("📁 Путь к базе данных", value="./data/chroma-db")
    
    # API ключ
    st.session_state.openrouter_key = st.text_input(
        "🔑 OpenRouter API Key (опционально)",
        type="password",
        help="Получи ключ на openrouter.ai/keys. Бесплатно 100 запросов/день"
    )
    
    if st.button("🔌 Загрузить базу данных", use_container_width=True):
        with st.spinner("Загружаю базу..."):
            try:
                st.session_state.db = get_db(db_path)
                st.success(f"✅ База загружена")
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")
    
    st.divider()
    
    st.subheader("📥 Добавить книгу")
    uploaded_file = st.file_uploader("Выбери текстовый файл", type=['txt'])
    
    if uploaded_file and st.session_state.db:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='wb') as f:
            f.write(uploaded_file.getvalue())
            temp_path = f.name
        
        if st.button("📖 Загрузить книгу", use_container_width=True):
            with st.spinner("Обрабатываю книгу..."):
                try:
                    ingest_book(temp_path, st.session_state.db)
                    st.success(f"✅ Книга загружена")
                except Exception as e:
                    st.error(f"❌ Ошибка: {e}")
                finally:
                    os.unlink(temp_path)
    
    st.divider()
    
    st.subheader("📊 Статус")
    if st.session_state.db:
        st.success("🟢 База данных готова")
        try:
            count = st.session_state.db._collection.count()
            st.info(f"📄 Документов в базе: {count}")
        except:
            pass
    else:
        st.warning("🟡 База не загружена")

# Основной интерфейс
st.title("📚 Чат с твоей библиотекой")

if st.session_state.db is None:
    st.warning("⚠️ Сначала загрузи базу данных в боковой панели!")
else:
    # История чата
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "sources" in message:
                with st.expander("📌 Источники"):
                    for source in message["sources"]:
                        st.caption(f"{source['book']} — {source['chapter']}")
                        st.text(source['text'][:200] + "...")
    
    # Поле ввода
    if prompt := st.chat_input("Спроси что-нибудь о книгах..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            with st.status("🔍 Ищу в книгах...", expanded=True) as status:
                # Поиск
                results = st.session_state.db.similarity_search(prompt, k=3)
                
                # Собираем контекст
                context_parts = []
                sources = []
                for doc in results:
                    book = doc.metadata.get('book', 'Неизвестно')
                    author = doc.metadata.get('author', 'Неизвестен')
                    chapter = doc.metadata.get('chapter', 'Неизвестно')
                    text = doc.page_content
                    
                    context_parts.append(f"[{book}, {chapter}]\n{text}")
                    sources.append({
                        "book": f"{author} - {book}",
                        "chapter": chapter,
                        "text": text
                    })
                
                context = "\n\n".join(context_parts)
                status.update(label="🤔 Формирую ответ...")
                
                # Если есть API ключ — используем генерацию
                if st.session_state.openrouter_key:
                    try:
                        prompt_for_llm = build_prompt(prompt, context)
                        
                        response = requests.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {st.session_state.openrouter_key}",
                                "Content-Type": "application/json"
                            },
                            json={
                                "model": "mistralai/mistral-7b-instruct:free",
                                "messages": [
                                    {"role": "user", "content": prompt_for_llm}
                                ],
                                "max_tokens": 512
                            },
                            timeout=60
                        )
                        
                        if response.status_code == 200:
                            answer = response.json()["choices"][0]["message"]["content"]
                            status.update(label="✅ Готово!", state="complete")
                        else:
                            answer = f"⚠️ Ошибка API: {response.status_code}\n\n**Найденные отрывки:**\n\n"
                            for src in sources:
                                answer += f"📖 **{src['book']}** — {src['chapter']}\n{src['text'][:400]}...\n\n"
                            status.update(label="⚠️ Ошибка API, показываю контекст", state="error")
                    
                    except Exception as e:
                        answer = f"⚠️ Ошибка: {e}\n\n**Найденные отрывки:**\n\n"
                        for src in sources:
                            answer += f"📖 **{src['book']}** — {src['chapter']}\n{src['text'][:400]}...\n\n"
                        status.update(label="❌ Ошибка", state="error")
                
                else:
                    # Нет API ключа — показываем контекст
                    answer = "**📖 Найденные отрывки:**\n\n"
                    for src in sources:
                        answer += f"📖 **{src['book']}** — {src['chapter']}\n{src['text'][:500]}...\n\n"
                    answer += "\n---\n*💡 Введи API ключ OpenRouter в боковой панели для генерации связных ответов*"
                    status.update(label="✅ Готово!", state="complete")
            
            st.markdown(answer)
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "sources": sources
            })
            st.rerun()

# Примеры вопросов
if not st.session_state.messages:
    st.divider()
    st.subheader("💡 Попробуй спросить:")
    
    col1, col2, col3 = st.columns(3)
    example_queries = [
        "О чём первая глава?",
        "Кто главный герой?",
        "Какие основные идеи?"
    ]
    
    for col, query in zip([col1, col2, col3], example_queries):
        if col.button(query, use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": query})
            st.rerun()
