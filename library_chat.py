import streamlit as st
import os
from pathlib import Path
import tempfile
# запуск streamlit run library_chat.py

# ИМПОРТЫ
from chunker import get_db, ingest_book
from  normalize import  build_prompt

# ===================== НАСТРОЙКИ СТРАНИЦЫ =====================
st.set_page_config(
    page_title="📚 Библиотечный RAG",
    page_icon="📖",
    layout="wide"
)

# ===================== ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ =====================
if "db" not in st.session_state:
    st.session_state.db = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "books_loaded" not in st.session_state:
    st.session_state.books_loaded = False

# ===================== БОКОВАЯ ПАНЕЛЬ =====================
with st.sidebar:
    st.title("⚙️ Управление библиотекой")

    # Путь к базе данных
    db_path = st.text_input("📁 Путь к базе данных", value="./chroma_db")

    # Кнопка загрузки базы
    if st.button("🔌 Загрузить базу данных", use_container_width=True):
        with st.spinner("Загружаю базу..."):
            try:
                st.session_state.db = get_db(db_path)
                st.session_state.books_loaded = True
                st.success(f"✅ База загружена из {db_path}")
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")

    st.divider()

    # ===== ЗАГРУЗКА НОВЫХ КНИГ =====
    st.subheader("📥 Добавить книгу")

    # Форма для загрузки файла
    uploaded_file = st.file_uploader(
        "Выбери текстовый файл",
        type=['txt'],
        help="Название файла должно быть в формате: Автор-Название.txt"
    )

    if uploaded_file and st.session_state.db:
        # Сохраняем временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='wb') as f:
            f.write(uploaded_file.getvalue())
            temp_path = f.name

        if st.button("📖 Загрузить книгу в базу", use_container_width=True):
            with st.spinner("Обрабатываю книгу..."):
                try:
                    ingest_book(temp_path, st.session_state.db)
                    st.success(f"✅ Книга '{uploaded_file.name}' загружена!")
                except Exception as e:
                    st.error(f"❌ Ошибка: {e}")
                finally:
                    os.unlink(temp_path)  # Удаляем временный файл

    st.divider()

    # Статус
    st.subheader("📊 Статус")
    if st.session_state.books_loaded:
        st.success("🟢 База данных готова")
        # Попытка получить количество документов
        try:
            count = st.session_state.db._collection.count()
            st.info(f"📄 Документов в базе: {count}")
        except:
            pass
    else:
        st.warning("🟡 База не загружена")

# ===================== ОСНОВНОЙ ИНТЕРФЕЙС =====================
st.title("📚 Чат с твоей библиотекой")

# Показываем предупреждение, если база не загружена
if not st.session_state.books_loaded:
    st.warning("⚠️ Сначала загрузи базу данных в боковой панели!")

# ===== ИСТОРИЯ ЧАТА =====
chat_container = st.container()

with chat_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            # Если есть источники, показываем их
            if "sources" in message:
                with st.expander("📌 Источники"):
                    for i, source in enumerate(message["sources"]):
                        st.caption(f"{source['book']} — {source['chapter']}")
                        st.text(source['text'][:200] + "...")

# ===== ПОЛЕ ВВОДА =====
if prompt := st.chat_input("Спроси что-нибудь о книгах..."):
    # Добавляем вопрос пользователя
    st.session_state.messages.append({"role": "user", "content": prompt})
with chat_container:
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if not st.session_state.books_loaded:
            st.error("❌ Сначала загрузи базу данных!")
            answer = "Ошибка: база данных не загружена"
            sources = []
        else:
            with st.status("🔍 Ищу в книгах...", expanded=True) as status:
                # 1. Поиск похожих документов
                results = st.session_state.db.similarity_search(prompt, k=3)

                # Собираем контекст и источники
                context_parts = []
                sources = []

                for i, doc in enumerate(results):
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

                # 2. Собираем промпт
                status.update(label="🤔 Формирую промпт...")
                prompt_for_llm = build_prompt(prompt)

                # 3. ТУТ БУДЕТ ВЫЗОВ НЕЙРОСЕТКИ
                # Пока просто показываем контекст
                status.update(label="📝 Готово!", state="complete")

                # ВРЕМЕННО: просто показываем найденные куски
                answer = "Нашел вот что:\n\n"
                for src in sources:
                    answer += f"📖 {src['book']} — *{src['chapter']}*\n"
                    answer += f"_{src['text'][:300]}..._\n\n"
                answer += "\n---\n*⚡ Подключите LLM для генерации ответов*"

        st.markdown(answer)

        # Сохраняем ответ в историю
        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "sources": sources if 'sources' in locals() else []
        })

# ===================== НИЖНЯЯ ПАНЕЛЬ С ПРИМЕРАМИ =====================
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
            # Имитируем ввод вопроса
            st.session_state.messages.append({"role": "user", "content": query})
            st.rerun()
