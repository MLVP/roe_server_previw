# Происхождение и права

Клиент, игровые бинарники, архивы ресурсов, реальные аккаунтные ключи/билеты и полные сетевые записи не включены. Фиксированные данные локального handshake16/32байта распространяются только в ring-of-elysium-local по прямому указанию владельца. Названия игры принадлежат их правообладателям; проект неофициальный. Для использования необходим собственный совместимый клиент. Код исходного лобби сохраняет MIT-уведомление в search/Ring-of-Elysium-Lobby-Emulator/LICENSE (в ring-of-elysium-local). Публичная адаптация LobbyPreData.cs убирает встроенный CK и читает локальный файл. Остальной авторский код пока без выбранной общей лицензии: общедоступность Git не предоставляет автоматически права на произвольное использование/перелицензирование. Перед открытым лицензированием владелец должен выбрать лицензию и проверить происхождение материалов; чужие права этим не изменяются.

## Демонстрационное использование и ответственность

Полное уведомление на английском и русском размещено в [README.md](README.md). Проект предназначен для личного домашнего демонстрационного использования и исследований, предоставляется «как есть»; все действия пользователь выполняет на свой риск. Владелец, авторы, сопровождающие и участники не несут ответственности в максимально допустимой применимым законодательством степени. Это не исключает неотменяемую по закону ответственность и не изменяет лицензии сторонних компонентов.

## Сторонний код: лицензия MIT (эмулятор лобби)

Базовая часть протокола лобби перенесена на Python в
`server/directory/lobby_login_2022.py` по мотивам MIT-реализации
эмулятора лобби (проект Ring-of-Elysium-Lobby-Emulator). Исходники на C#
из проекта удалены, но уведомление об авторских правах и текст лицензии
сохранены здесь, как того требует MIT.

```
MIT License

Copyright (c) 2026 blip-rgb

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
