from typing import NamedTuple


class Origin(NamedTuple):
    country: str
    weight: float
    women: tuple[str, ...]
    men: tuple[str, ...]
    surnames: tuple[str, ...]


class Group(NamedTuple):
    name: str
    weight: float
    youngest: int
    titles: tuple[str, ...]


class Span(NamedTuple):
    text: str
    youngest: int
    oldest: int
    weight: float = 1


ORIGINS = (
    Origin(
        "England",
        10,
        ("Sarah", "Emma", "Claire", "Rachel", "Helen", "Laura", "Joanne", "Karen"),
        ("David", "Mark", "Daniel", "Thomas", "Andrew", "Gary", "Simon", "Stephen"),
        ("Smith", "Jones", "Taylor", "Brown", "Wilson", "Walker", "Wright", "Hughes", "Clarke"),
    ),
    Origin(
        "Scotland",
        3,
        ("Fiona", "Morag", "Catriona", "Shona", "Kirsty", "Eilidh", "Lorna", "Isla"),
        ("Iain", "Alasdair", "Callum", "Fraser", "Duncan", "Hamish", "Euan", "Craig"),
        ("Macdonald", "Campbell", "Stewart", "Robertson", "Murray", "Mackay", "Reid", "Ross"),
    ),
    Origin(
        "Ireland",
        3,
        ("Siobhán", "Aoife", "Niamh", "Gráinne", "Mary", "Orla", "Ciara", "Bríd"),
        ("Seán", "Ciarán", "Pádraig", "Declan", "Eoin", "Cathal", "Liam", "Donal"),
        ("Murphy", "Kelly", "O'Sullivan", "Walsh", "Byrne", "Ryan", "Doyle", "Kavanagh", "Quinn"),
    ),
    Origin(
        "Poland",
        4,
        ("Agnieszka", "Katarzyna", "Magdalena", "Joanna", "Ewa", "Monika", "Zofia", "Barbara"),
        ("Piotr", "Tomasz", "Krzysztof", "Paweł", "Marek", "Andrzej", "Jakub", "Grzegorz"),
        ("Nowak", "Wójcik", "Kowalczyk", "Woźniak", "Mazur", "Krawczyk", "Kaczmarek", "Zając"),
    ),
    Origin(
        "Romania",
        3,
        ("Elena", "Ioana", "Andreea", "Mihaela", "Gabriela", "Alina", "Roxana", "Simona"),
        ("Andrei", "Ion", "Mihai", "Alexandru", "Gheorghe", "Florin", "Adrian", "Bogdan"),
        ("Popescu", "Ionescu", "Popa", "Dumitru", "Stan", "Stoica", "Munteanu", "Lazăr"),
    ),
    Origin(
        "Germany",
        3,
        ("Sabine", "Katrin", "Anja", "Claudia", "Stefanie", "Julia", "Petra", "Birgit"),
        ("Jürgen", "Stefan", "Andreas", "Frank", "Matthias", "Jan", "Uwe", "Klaus"),
        ("Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker"),
    ),
    Origin(
        "Italy",
        3,
        ("Giulia", "Francesca", "Chiara", "Silvia", "Paola", "Rosa", "Valentina", "Lucia"),
        ("Marco", "Giuseppe", "Luca", "Alessandro", "Francesco", "Matteo", "Stefano", "Antonio"),
        ("Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci"),
    ),
    Origin(
        "Spain",
        3,
        ("Carmen", "Lucía", "Marta", "Pilar", "Nuria", "Cristina", "Rocío", "Inés"),
        ("Carlos", "Pablo", "Sergio", "Manuel", "Jorge", "Álvaro", "Raúl", "Iñaki"),
        ("García", "Fernández", "Martínez", "Gómez", "Ruiz", "Díaz", "Moreno", "Navarro"),
    ),
    Origin(
        "Turkey",
        3,
        ("Ayşe", "Fatma", "Elif", "Zeynep", "Emine", "Hatice", "Merve", "Selin"),
        ("Mehmet", "Mustafa", "Ahmet", "Emre", "Murat", "Hasan", "Burak", "Kemal"),
        ("Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Aydın", "Öztürk", "Arslan"),
    ),
    Origin(
        "Nigeria",
        4,
        ("Funmilayo", "Folake", "Bisola", "Yetunde", "Adunni", "Titilayo", "Kemi", "Abosede"),
        ("Babatunde", "Oluwaseun", "Femi", "Tunde", "Adewale", "Kayode", "Olumide", "Segun"),
        ("Adeyemi", "Balogun", "Adebayo", "Ogunleye", "Afolabi", "Adeleke", "Ogundipe", "Akinola"),
    ),
    Origin(
        "Ghana",
        3,
        ("Abena", "Akosua", "Ama", "Efua", "Yaa", "Adwoa", "Esi", "Afua"),
        ("Kwame", "Kwabena", "Yaw", "Kwasi", "Kojo", "Kwaku", "Ekow", "Fiifi"),
        ("Asante", "Owusu", "Boateng", "Osei", "Agyeman", "Appiah", "Darko", "Amoah", "Ofori"),
    ),
    Origin(
        "Kenya",
        3,
        ("Grace", "Mercy", "Faith", "Esther", "Joyce", "Lucy", "Caroline", "Beatrice"),
        ("John", "Peter", "Joseph", "Samuel", "Brian", "Dennis", "Moses", "Collins"),
        ("Kamau", "Otieno", "Mwangi", "Odhiambo", "Njoroge", "Ochieng", "Mutua", "Kariuki"),
    ),
    Origin(
        "Jamaica",
        3,
        ("Marcia", "Sharon", "Shanice", "Simone", "Paulette", "Tanisha", "Andrea", "Denise"),
        ("Delroy", "Winston", "Devon", "Lloyd", "Andre", "Marlon", "Clive", "Errol"),
        ("Campbell", "Williams", "Thompson", "Gordon", "Grant", "Francis", "Morgan", "Reid"),
    ),
    Origin(
        "India",
        6,
        ("Anjali", "Sunita", "Kavita", "Neha", "Pooja", "Rekha", "Meera", "Deepa"),
        ("Rajesh", "Amit", "Sanjay", "Vikram", "Rahul", "Arjun", "Suresh", "Anil"),
        ("Sharma", "Gupta", "Verma", "Patel", "Kumar", "Mehta", "Joshi", "Agarwal", "Nair"),
    ),
    Origin(
        "Pakistan",
        4,
        ("Ayesha", "Fatima", "Sana", "Nadia", "Rabia", "Hina", "Saima", "Zainab"),
        ("Bilal", "Tariq", "Usman", "Faisal", "Asif", "Kamran", "Hamza", "Adnan"),
        ("Khan", "Ahmed", "Hussain", "Malik", "Iqbal", "Butt", "Qureshi", "Chaudhry", "Raza"),
    ),
    Origin(
        "China",
        6,
        ("Fang", "Xiulan", "Mei", "Jing", "Yan", "Hui", "Ling", "Xiaoyu"),
        ("Wei", "Jun", "Lei", "Hao", "Ming", "Qiang", "Jian", "Zhiwei"),
        ("Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu", "Zhou"),
    ),
    Origin(
        "Vietnam",
        3,
        ("Linh", "Lan", "Hương", "Thảo", "Mai", "Ngọc", "Trang", "Hoa"),
        ("Minh", "Tuấn", "Hùng", "Dũng", "Quang", "Huy", "Thanh", "Long"),
        ("Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Phan", "Vũ", "Bùi", "Đỗ"),
    ),
    Origin(
        "the Philippines",
        4,
        ("Maricel", "Rowena", "Jocelyn", "Analyn", "Marites", "Cristina", "Rhea", "Lourdes"),
        ("Jose", "Rodel", "Arnel", "Jomar", "Ramon", "Rogelio", "Danilo", "Efren"),
        ("Santos", "Reyes", "Cruz", "Bautista", "Mendoza", "Villanueva", "Ramos", "Pascual"),
    ),
    Origin(
        "Japan",
        2,
        ("Yuko", "Keiko", "Naoko", "Akiko", "Haruka", "Misaki", "Tomoko", "Ayumi"),
        ("Takashi", "Hiroshi", "Kenji", "Daisuke", "Shota", "Kazuo", "Makoto", "Ryota"),
        ("Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Kobayashi", "Kato"),
    ),
    Origin(
        "South Korea",
        2,
        ("Jiyeon", "Minjung", "Soojin", "Eunji", "Hyejin", "Seoyeon", "Mikyung", "Jihye"),
        ("Minjun", "Jihoon", "Sungmin", "Donghyun", "Jaewon", "Hyunwoo", "Sanghoon", "Youngho"),
        ("Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim"),
    ),
    Origin(
        "Iran",
        2,
        ("Maryam", "Zahra", "Fatemeh", "Niloufar", "Shirin", "Leila", "Parisa", "Sara"),
        ("Reza", "Mohammad", "Hossein", "Mehdi", "Amir", "Babak", "Dariush", "Kaveh"),
        ("Hosseini", "Ahmadi", "Mohammadi", "Karimi", "Rezaei", "Moradi", "Jafari", "Rahimi"),
    ),
    Origin(
        "Brazil",
        3,
        ("Ana", "Juliana", "Fernanda", "Patrícia", "Camila", "Luciana", "Adriana", "Beatriz"),
        ("João", "Rafael", "Lucas", "Marcelo", "Leandro", "Rodrigo", "Paulo", "Gustavo"),
        ("Silva", "Oliveira", "Souza", "Costa", "Pereira", "Almeida", "Carvalho", "Ribeiro"),
    ),
    Origin(
        "Mexico",
        3,
        ("Guadalupe", "Verónica", "Alejandra", "Gabriela", "Leticia", "Daniela", "Araceli"),
        ("Juan", "Miguel", "Alejandro", "Jorge", "Arturo", "Fernando", "Ricardo", "Rubén"),
        ("Hernández", "López", "González", "Rodríguez", "Pérez", "Sánchez", "Ramírez", "Flores"),
    ),
    Origin(
        "the United States",
        3,
        ("Jennifer", "Jessica", "Ashley", "Amanda", "Melissa", "Heather", "Kimberly", "Nicole"),
        ("Christopher", "Matthew", "Joshua", "Brian", "Jason", "Kevin", "Ryan", "Tyler"),
        ("Johnson", "Miller", "Davis", "Anderson", "Martin", "White", "Harris", "Lewis"),
    ),
)

# Rough shares of EU employment by ISCO-08 major group, from Eurostat's labour force survey.
OCCUPATIONS = (
    Group(
        "managers",
        5.2,
        25,
        (
            "shop manager",
            "hotel manager",
            "restaurant manager",
            "care home manager",
            "office manager",
            "sales manager",
            "head teacher",
            "warehouse manager",
        ),
    ),
    Group(
        "professionals",
        21.4,
        23,
        (
            "primary school teacher",
            "secondary school maths teacher",
            "nurse",
            "GP",
            "hospital doctor",
            "accountant",
            "software developer",
            "solicitor",
            "civil engineer",
            "pharmacist",
            "social worker",
            "university lecturer",
            "physiotherapist",
            "midwife",
            "librarian",
        ),
    ),
    Group(
        "technicians and associate professionals",
        16.2,
        19,
        (
            "paramedic",
            "lab technician",
            "paralegal",
            "estate agent",
            "bookkeeper",
            "IT support technician",
            "chef",
            "dental hygienist",
            "insurance broker",
            "electrical engineering technician",
            "fitness instructor",
            "building inspector",
        ),
    ),
    Group(
        "clerical support workers",
        9.3,
        16,
        (
            "receptionist",
            "bank clerk",
            "payroll clerk",
            "call centre agent",
            "school secretary",
            "post office counter clerk",
            "stock control clerk",
            "library assistant",
        ),
    ),
    Group(
        "service and sales workers",
        16.4,
        16,
        (
            "shop assistant",
            "supermarket cashier",
            "hairdresser",
            "care worker",
            "waiter",
            "cook",
            "security guard",
            "police officer",
            "childminder",
            "bartender",
            "teaching assistant",
            "market stall trader",
        ),
    ),
    Group(
        "skilled agricultural, forestry and fishery workers",
        3.4,
        16,
        ("dairy farmer", "market gardener", "fishing boat deckhand", "sheep farmer", "forester"),
    ),
    Group(
        "craft and related trades workers",
        11.4,
        16,
        (
            "electrician",
            "plumber",
            "carpenter",
            "bricklayer",
            "car mechanic",
            "welder",
            "baker",
            "butcher",
            "painter and decorator",
            "roofer",
            "plasterer",
        ),
    ),
    Group(
        "plant and machine operators and assemblers",
        7.6,
        18,
        (
            "bus driver",
            "lorry driver",
            "taxi driver",
            "forklift driver",
            "factory machine operator",
            "train driver",
            "delivery van driver",
            "crane operator",
        ),
    ),
    Group(
        "elementary occupations",
        8.6,
        16,
        (
            "cleaner",
            "kitchen porter",
            "warehouse picker",
            "building labourer",
            "refuse collector",
            "fruit picker",
            "street sweeper",
            "hotel housekeeper",
        ),
    ),
    Group("armed forces", 0.5, 17, ("army corporal", "navy engineer")),
)

STUDENTS = (
    "nursing student",
    "law student",
    "engineering student",
    "history student",
    "apprentice electrician",
    "trainee accountant",
)

NOT_WORKING = (
    Span("unemployed", 16, 65),
    Span("full-time carer", 18, 65),
    Span("full-time parent", 20, 50),
    Span("off work long-term sick", 20, 65),
)

ARRIVALS = (
    Span("with their family", 1, 15, 3),
    Span("for university, and stayed", 18, 19),
    Span("for a job", 20, 60, 4),
    Span("for a partner's job", 22, 60, 2),
    Span("to move in with a partner", 20, 60, 2),
    Span("because the rent was cheap", 19, 50, 2),
    Span("for a fresh start after a divorce", 28, 65),
    Span("to look after an elderly parent", 35, 65),
    Span("to be near their grown-up children", 55, 80),
    Span("when they retired", 60, 75),
    Span("into social housing they were offered", 19, 70),
    Span("after inheriting a flat here", 25, 75),
)

EVENTS = (
    Span("their parents divorced", 3, 15),
    Span("lost a parent", 4, 16),
    Span("went to live with a grandparent", 2, 12),
    Span("bullied badly at school", 9, 15),
    Span("a long illness kept them out of school for a year", 6, 14),
    Span("won a scholarship to a selective school", 10, 12),
    Span("their family lost its home", 5, 16),
    Span("left school to start work", 15, 17),
    Span("first in their family to go to university", 18, 19),
    Span("dropped out of university", 19, 21),
    Span("joined the army", 17, 22),
    Span("became a parent unexpectedly young", 16, 19),
    Span("won a regional championship in their sport", 13, 28),
    Span("came out to their family", 14, 40),
    Span("spent eight months in prison", 18, 40),
    Span("homeless for several months", 17, 45),
    Span("married", 20, 45),
    Span("had their first child", 20, 42),
    Span("adopted a child", 28, 45),
    Span("lost a baby before it was born", 22, 42),
    Span("their marriage ended in divorce", 26, 62),
    Span("widowed", 35, 78),
    Span("an affair nearly ended their marriage", 28, 60),
    Span("made redundant", 22, 62),
    Span("a business they started went bust", 25, 60),
    Span("promoted to run the place they worked", 28, 58),
    Span("changed career completely", 28, 55),
    Span("went back to study as an adult", 25, 55),
    Span("reported their employer for fraud and lost their job", 25, 60),
    Span("an unexpected inheritance", 18, 75),
    Span("won a modest lottery prize", 18, 75),
    Span("lost their savings in a bad investment", 30, 68),
    Span("treated for cancer, now in remission", 25, 76),
    Span("a car crash and a long recovery", 17, 70),
    Span("a long spell of depression", 16, 65),
    Span("stopped drinking after years of drinking too much", 25, 60),
    Span("years caring for a sick parent", 30, 65),
    Span("a close friend betrayed them", 16, 60),
    Span("fell out with a brother or sister and stopped speaking", 18, 65),
    Span("a fire destroyed most of what they owned", 10, 75),
    Span("found religion", 16, 65),
    Span("lost their faith", 16, 55),
    Span("fostered children for several years", 30, 60),
    Span("became a grandparent", 42, 78),
    Span("a grown child stopped speaking to them", 42, 78),
    Span("a parent died", 25, 70),
)
