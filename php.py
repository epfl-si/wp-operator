def php_double_quoted_escape(s: str) -> str:
    def escape_char(c):
        if c == '\\':
            return '\\\\'
        elif c == '"':
            return '\\"'
        elif c == '$':
            return '\\$'
        elif c == '\n':
            return '\\n'
        elif c == '\r':
            return '\\r'
        elif c == '\t':
            return '\\t'
        elif c == '\v':
            return '\\v'
        elif c == '\f':
            return '\\f'
        elif ord(c) < 32 or ord(c) >= 127:
            return '\\x{:02x}'.format(ord(c))
        else:
            return c
    escaped = ''.join(escape_char(c) for c in s)
    return f'"{escaped}"'


def phpize(struct):
    if type(struct) == str:
        return php_double_quoted_escape(struct)
    elif type(struct) in (int, float):
        return str(struct)
    elif type(struct) == bool:
        return 'TRUE' if struct else 'FALSE'
    elif type(struct) == list:
        phpized_items = [phpize(s) for s in struct]
        return f'''array({', '.join(phpized_items)})'''
    elif type(struct) == dict:
        phpized_items = [f'''{phpize(k)} => {phpize(struct[k])}''' for k in struct.keys()]
        return f'''array({', '.join(phpized_items)})'''
    else:
        raise ValueError(str(struct))


if __name__ == "__main__":
    assert phpize("test") == '''"test"'''
    assert phpize(['test', 'test1', 'test2', ['test3', 'test4', 2, 5, 6], True, False]) == '''array("test", "test1", "test2", array("test3", "test4", 2, 5, 6), TRUE, FALSE)'''
    assert phpize(['test', 'test1', 'test2', ['test3', 'test4', {"rosa": "rosaOK", "Dom": "DomOK", "Nicolas": 222}, 5, 6], True, False]) == '''array("test", "test1", "test2", array("test3", "test4", array("rosa" => "rosaOK", "Dom" => "DomOK", "Nicolas" => 222), 5, 6), TRUE, FALSE)'''
    assert phpize({'a': [[1]]}) == '''array("a" => array(array(1)))'''

