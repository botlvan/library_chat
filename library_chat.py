import streamlit as st
import os
import tempfile
import re
from typing import Optional
from transformers import AutoTokenizer, AutoConfig, AutoModelForCausalLM, pipeline
import torch

from chunker import get_db, ingest_book
from normalize import build_prompt


def extract_chapter(query: str) -> Optional[str]:
    """Извлекает номер главы из запроса."""
    query_lower = query.lower()
    
    numbers = re.findall(r'\b(\d+)\b', query_lower)
    if numbers:
        num = int(numbers[0])
        if 1 <= num <= 10:
            words = ['первая', 'вторая', 'третья', 'четвертая', 'пятая', 
                     'шестая', 'седьмая', 'восьмая', 'девятая', 'десятая']
            return words[num - 1]
    
    words = ['первая', 'вторая', 'третья', 'четвертая', 'пятая', 
             'шестая', 'седьмая', 'восьмая', 'девятая', 'десятая']
    for word in words:
        if word in query_lower:
            return word
    return None


def load_local_model(model_name: str = "microsoft/Phi-3-mini-4k-instruct") -> dict:
    """Загрузка локальной модели Phi-3."""
    try:
        with st.spinner("Загружаю модель Phi-3 (первые 2-3 минуты могут быть долгими)..."):
            config = AutoConfig.from_pretrained(model_name, trust_remote_code=True)
            if hasattr(config, "rope_scaling"):
                config.rope_scaling = None
            config.use_cache = False
            
            tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            tokenizer.padding_side = "left"
            
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                config=config,
                trust_remote_code=True,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True,
                device_map="cpu"
            )
            
            pipe = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                max_new_tokens=1024,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                use_cache=False,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.pad_token_id,
            )
            
            st.success("✅ Модель загружена!")
            return {
                "tokenizer": tokenizer,
                "pipeline": pipe
            }
    except Exception as e:
        st.error(f"❌ Ошибка загрузки модели: {e}")
        return None


# ===================== НАСТРОЙКИ СТРАНИЦЫ =====================
st.set_page_config(
    page_title="📚 Библиотечный RAG",
    page_icon="📖",
    layout="wide"
)

# ===================== ИНИЦИАЛИЗАЦИЯ =====================
if "db" not in st.session_state:
    st.session_state.db = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "books_loaded" not in st.session_state:
    st.session_state.books_loaded = False
if "llm" not in st.session_state:
    st.session_state.llm = None

# ===================== БОКОВАЯ ПАНЕЛЬ =====================
with st.sidebar:
    st.title("⚙️ Управление библиотекой")
    
    db_path = st.text_input("📁 Путь к базе данных", value="./data/chroma-db")
    
    if st.button("🔌 Загрузить базу данных", use_container_width=True):
        with st.spinner("Загружаю базу..."):
            try:
                st.session_state.db = get_db(db_path)
                st.session_state.books_loaded = True
                st.success(f"✅ База загружена из {db_path}")
                
                # Автоматически загружаем модель
                if st.session_state.llm is None:
                    st.session_state.llm = load_local_model()
                    
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")
    
    st.divider()
    
    # Перезагрузка модели
    if st.session_state.books_loaded:
        if st.button("🔄 Перезагрузить модель", use_container_width=True):
            st.session_state.llm = load_local_model()
    
    st.divider()
    
    # Загрузка книги
    st.subheader("📥 Добавить книгу")
    uploaded_file = st.file_uploader(
        "Выбери текстовый файл",
        type=['txt'],
        help="Название: Автор-Название.txt"
    )
    
    if uploaded_file and st.session_state.db:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='wb') as f:
            f.write(uploaded_file.getvalue())
            temp_path = f.name
        
        if st.button("📖 Загрузить книгу", use_container_width=True):
            with st.spinner("Обрабатываю книгу..."):
                try:
                    ingest_book(temp_path, st.session_state.db)
                    st.success(f"✅ Книга '{uploaded_file.name}' загружена!")
                except Exception as e:
                    st.error(f"❌ Ошибка: {e}")
                finally:
                    os.unlink(temp_path)
    
    st.divider()
    
    # Статус
    st.subheader("📊 Статус")
    if st.session_state.books_loaded:
        st.success("🟢 База данных готова")
        if st.session_state.llm:
            st.success("🟢 Модель Phi-3 загружена")
        else:
            st.warning("🟡 Модель не загружена")
        try:
            count = st.session_state.db._collection.count()
            st.info(f"📄 Документов: {count}")
        except:
            pass
    else:
        st.warning("🟡 База не загружена")


# ===================== ОСНОВНОЙ ИНТЕРФЕЙС =====================
st.title("📚 Чат с твоей библиотекой")

if not st.session_state.books_loaded:
    st.warning("⚠️ Сначала загрузи базу данных в боковой панели!")

# История чата
chat_container = st.container()
with chat_container:
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
    
    with chat_container:
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            if not st.session_state.books_loaded or st.session_state.db is None:
                st.error("❌ База данных не загружена!")
                answer = "Ошибка: база данных не загружена"
                sources = []
            elif st.session_state.llm is None:
                st.error("❌ Модель не загружена! Нажми 'Загрузить базу данных'")
                answer = "Ошибка: модель не загружена"
                sources = []
            else:
                with st.status("🔍 Ищу в книгах...", expanded=True) as status:
                    # Поиск
                    results = st.session_state.db.similarity_search(prompt, k=5)
                    
                    # Фильтр по главе
                    chapter = extract_chapter(prompt)
                    if chapter:
                        results = [r for r in results if chapter in r.metadata.get('chapter', '').lower()]
                    
                    results = results[:3]
                    
                    # Сбор контекста
                    context_parts = []
                    sources = []
                    for doc in results:
                        book = doc.metadata.get('book', 'Неизвестно')
                        author = doc.metadata.get('author', 'Неизвестен')
                        chapter_name = doc.metadata.get('chapter', 'Неизвестно')
                        text = doc.page_content
                        
                        context_parts.append(f"[{book}, {chapter_name}]\n{text}")
                        sources.append({
                            "book": f"{author} - {book}",
                            "chapter": chapter_name,
                            "text": text
                        })
                    
                    context = "\n\n".join(context_parts)
                    
                    # Генерация ответа
                    status.update(label="🤔 Формирую ответ...")
                    prompt_for_llm = build_prompt(prompt, context)
                    
                    try:
                        tokenizer = st.session_state.llm["tokenizer"]
                        pipe = st.session_state.llm["pipeline"]
                        
                        messages = [
                            {"role": "system", "content": "Ты — помощник, отвечающий на вопросы по книгам. Отвечай кратко и по делу."},
                            {"role": "user", "content": prompt_for_llm}
                        ]
                        
                        prompt_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                        
                        outputs = pipe(
                            prompt_text,
                            max_new_tokens=2048,
                            do_sample=True,
                            temperature=0.7,
                            top_p=0.95,
                            eos_token_id=tokenizer.eos_token_id,
                            pad_token_id=tokenizer.pad_token_id
                        )
                        
                        full_response = outputs[0]["generated_text"]
                        if "ОТВЕТ:" in full_response:
                            answer = full_response.split("ОТВЕТ:")[-1].strip()
                        else:
                            answer = full_response.split(prompt_text)[-1].strip()
                        
                        status.update(label="✅ Готово!", state="complete")
                        
                    except Exception as e:
                        answer = f"⚠️ Ошибка генерации: {e}\n\nКонтекст:\n{context[:500]}..."
                        status.update(label="❌ Ошибка", state="error")
            
            st.markdown(answer)
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "sources": sources if 'sources' in locals() else []
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
