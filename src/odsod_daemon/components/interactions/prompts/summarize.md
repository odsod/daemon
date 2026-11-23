Summarize the supplied transcript.
Write in English, also for {{ languages | join(', ') }} talk.
Write the title, overview, and every point's text entirely in English.
Translate Swedish facts into English in the summary. Keep people's names
and glossary terms unchanged. Never output a translated transcript.
Use only what the transcript says;
leave a point out when unsure. Write an overview of 1 to 3 sentences.
Use points only under Decided, Insight, Problem, Context, Next.
Leave out labels with nothing to say. A Next point names its owner when the
transcript names one. Notes are {{ owner_name }}'s own context.
Lines from Others may be several people; never guess who.
Use at most {{ title_max_words }} words in the title.
Set skip true only for greetings or noise with no substance.
Return the summary as JSON matching the supplied schema.
Glossary terms keep their spelling. Most important terms are last:
{{ glossary | join(', ') }}
