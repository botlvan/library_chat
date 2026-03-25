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
    
    status.update(label="✅ Найдено!", state="complete")
    
    # Формируем ответ из контекста (без генерации)
    answer = "**📖 Найденные отрывки:**\n\n"
    for src in sources:
        answer += f"**{src['book']}** — *{src['chapter']}*\n"
        answer += f"{src['text'][:500]}...\n\n"
    answer += "\n---\n*⚡ Модель генерации настраивается, пока показываем точные совпадения из книг*"
