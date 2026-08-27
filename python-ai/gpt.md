Для такой задачи я бы **не начинал со skill**. Если цель — один раз глубоко разобраться в конкретном Python-плагине для Ansible, наиболее эффективно:

1. открыть **весь репозиторий** в Codex;
2. дать Codex задачу именно на **reverse engineering / codebase understanding**, а не «объясни этот файл»;
3. запретить изменения кода на первом этапе;
4. заставить его давать ссылки на **файлы, классы, функции и call flow**;
5. затем разбирать отдельные цепочки выполнения.

Это соответствует и текущим рекомендациям OpenAI: Codex хорошо подходит для задачи *Understand large codebases*, а постоянный контекст проекта лучше держать в `AGENTS.md`. Skills полезнее для **повторяемого workflow**, который вы хотите применять к разным репозиториям. ([OpenAI Developers][1])

### Я бы начал с такого промпта

# Reverse engineering Ansible Python plugin

I need to understand this repository, not modify it.

The repository contains a Python plugin/component used by Ansible.

Your task is to reverse-engineer how it works and teach it to me as if I am an engineer who needs to maintain and debug it.

Do NOT modify any files yet.

First inspect the entire relevant codebase. Do not limit yourself to the file I happen to have open.

Produce the analysis in the following stages.

## 1. Repository map

Identify:

* main Python packages and modules
* Ansible plugin entry points
* important classes and functions
* configuration files
* tests
* external dependencies
* Ansible-specific APIs being used

For every important item give the file path.

## 2. Plugin type and Ansible integration

Determine exactly what type of Ansible plugin/component this is:

* module
* action plugin
* lookup plugin
* filter plugin
* connection plugin
* callback plugin
* inventory plugin
* module_utils helper
* collection component
* or something else

Explain how Ansible discovers and invokes it.

Point me to the exact entry point in the source code.

## 3. Execution flow

Trace a normal execution from beginning to end.

Start from the moment Ansible invokes the plugin and follow the call chain.

Show it in this form:

Ansible
→ entry point
→ function/class
→ helper
→ external API/system
→ result processing
→ return to Ansible

For every step include:

* file path
* function/class name
* purpose
* important inputs
* important outputs

## 4. Data flow

Explain what data enters the plugin and how it changes.

Pay particular attention to:

* task/module arguments
* variables
* environment variables
* inventory/hostvars
* credentials
* files
* subprocess calls
* HTTP/API requests
* return values
* exceptions

Show the important data structures where useful.

## 5. Important Python mechanisms

Find Python constructs that are important for understanding the code, for example:

* inheritance
* decorators
* context managers
* generators
* dynamic imports
* monkey patching
* callbacks
* metaprogramming
* async code
* subprocesses

Explain them in the context of this codebase rather than generically.

## 6. Important Ansible mechanisms

Explain every non-obvious Ansible concept used by this project.

For example:

* AnsibleModule
* ActionBase
* module_utils
* plugin loader
* templating
* task_vars
* connection objects
* check mode
* diff mode
* facts
* collections
* DOCUMENTATION / EXAMPLES / RETURN

For each mechanism explain why this repository uses it.

## 7. External interactions

Identify everything outside Python that the plugin communicates with:

* REST APIs
* operating system
* shell commands
* files
* sockets
* databases
* cloud APIs
* network devices

Trace where those interactions originate.

## 8. Error handling

Explain:

* where exceptions originate
* which exceptions are caught
* which are propagated
* how errors are converted into Ansible failures
* retry logic
* cleanup logic

Identify areas where debugging could be difficult.

## 9. Tests

Find the tests that best demonstrate intended behavior.

Map important tests to the production functions they exercise.

Tell me which 3–5 tests I should read first to understand the project.

## 10. Mental model

Finally give me a concise mental model of the whole system:

"What this plugin fundamentally does is..."

Then provide:

### Five most important files to read

in recommended reading order.

### Five most important functions/classes

with one-line explanations.

### Questions I should be able to answer

Give me 10 questions that will test whether I actually understand the codebase.

## Rules

* Base conclusions on the repository, not assumptions.
* When uncertain, say so and show what evidence is missing.
* Always reference concrete file paths and symbols.
* Distinguish observed behavior from inferred behavior.
* Do not modify the repository.
* Do not propose refactoring yet.
* Prefer tracing real call paths over summarizing files independently.

Особенно важна последняя инструкция **«trace real call paths rather than summarizing files independently»**. Без неё агент часто начинает делать красивое, но мало полезное перечисление `foo.py содержит Foo, bar.py содержит Bar`.

### После первого прохода — не просите «расскажи подробнее»

Лучше задавать узкие задачи. Например:

```text
Now focus only on the execution path for <plugin/function>.

Trace it linearly from the Ansible entry point until the final result.

For every function call show:
file:line / symbol
inputs
outputs
side effects

Ignore unrelated parts of the repository.

At the end draw a compact call graph.
```

А потом, например:

```text
I don't understand why this code needs ActionBase and a separate module.

Explain the division of responsibilities using THIS repository only.

Compare the action plugin and module side by side and trace which code executes
on the Ansible controller and which executes on the managed host.
```

Для Ansible это особенно полезно: часто самое сложное — понять не сам Python, а **где выполняется конкретный кусок кода: controller vs managed node**, что делает action plugin, что делает module, где `module_utils`, откуда берутся `task_vars` и т. п.

### А нужен ли Skill?

Если это **один плагин**, я бы пока не делал skill.

Если вам предстоит разбирать **10–20 разных Python/Ansible проектов**, тогда skill уже имеет смысл. Codex Skills предназначены именно для повторяемых специализированных workflow; Codex может вызывать их явно через `$skill-name` или автоматически по описанию. Skill состоит прежде всего из `SKILL.md`, а встроенный `$skill-creator` умеет создать его за вас. ([ChatGPT Learn][2])

Я бы сделал skill примерно с такой специализацией:

```text
name: ansible-codebase-explainer

Purpose:
Reverse-engineer unfamiliar Python Ansible plugins and collections.

Workflow:
1. Identify plugin type.
2. Locate Ansible entry points.
3. Separate controller-side and managed-host execution.
4. Build repository map.
5. Trace real execution paths.
6. Trace data flow.
7. Identify Ansible APIs.
8. Map tests to implementation.
9. Produce recommended reading order.
10. Never modify code unless explicitly requested.
```

И создать его можно прямо из Codex:

```text
$skill-creator

Create a skill called ansible-codebase-explainer.

It should be used when I ask to understand, reverse-engineer, debug,
or learn an unfamiliar Python codebase implementing Ansible plugins,
modules, module_utils, or collections.

The skill must focus on call-flow analysis rather than file summaries...
```

Codex официально рекомендует держать skill **узким — одна конкретная работа на skill**, а инструкции писать как чёткие шаги с определёнными входами и выходами. ([ChatGPT Learn][2])

### Ещё полезнее для конкретного репозитория: `AGENTS.md`

Skill отвечает на вопрос **«как я обычно хочу анализировать код»**, а `AGENTS.md` — **«что Codex должен знать именно об этом проекте»**.

Codex читает `AGENTS.md` перед работой с репозиторием и позволяет иметь как root-инструкции, так и более локальные инструкции в подкаталогах. ([ChatGPT Learn][3])

Например, после первого анализа можно попросить:

```text
Based on what you learned about this repository, draft a concise AGENTS.md
for future code-analysis sessions.

Include only stable facts:
- project purpose
- architecture
- important entry points
- controller vs managed-host boundaries
- test commands
- important constraints

Do not include temporary observations or guesses.
```

OpenAI отдельно рекомендует не превращать `AGENTS.md` в огромную энциклопедию: лучше дать агенту **карту репозитория, а не тысячестраничную инструкцию**. ([OpenAI][4])

### Моя рекомендуемая схема

Для вашей задачи я бы сделал так:

**Codex + весь repo → большой промпт выше → call-flow конкретного сценария → вопросы по непонятным местам → только потом debugging/refactoring.**

И только если такой анализ станет регулярным:

**`ansible-codebase-explainer` skill + небольшой `AGENTS.md` в каждом проекте.**

Если хотите, можете **прикрепить сюда сам Python-файл или лучше весь Ansible-плагин/репозиторий ZIP**. Я могу на его примере составить **очень конкретный prompt для Codex именно под его структуру** — с названиями файлов, точками входа и тем, что Codex должен исследовать в первую очередь.

[1]: https://developers.openai.com/codex/use-cases?category=engineering&category=evaluation&category=quality&category=sciences&task_type=analysis&task_type=design&task_type=workflow&team=engineering&team=finance&team=operations&team=research&team=sales&utm_source=chatgpt.com "Codex use cases"
[2]: https://learn.chatgpt.com/codex/build-skills "Build skills | ChatGPT Learn"
[3]: https://learn.chatgpt.com/codex/agent-configuration/agents-md "Custom instructions with AGENTS.md | ChatGPT Learn"
[4]: https://openai.com/index/harness-engineering/?utm_source=chatgpt.com "Harness engineering: leveraging Codex in an agent-first world | OpenAI"
