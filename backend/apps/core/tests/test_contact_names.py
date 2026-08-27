"""Teste da função de quebra de nome usada pela migração 0048 (issue #55, FDD 001).

Sem `django_test_migrations` no projeto (não é dependência existente e o spec pede para não
adicionar uma nova), o teste exercita a função pura diretamente — é para isso que ela foi
extraída para `apps/core/contact_names.py`.
"""

from apps.core.contact_names import split_full_name


def test_split_full_name_dois_nomes():
    assert split_full_name("Daniel Pilar") == ("Daniel", "Pilar")


def test_split_full_name_tres_nomes_mantem_sobrenome_inteiro():
    assert split_full_name("Ana Paula Sá") == ("Ana", "Paula Sá")


def test_split_full_name_um_nome_so():
    assert split_full_name("Madonna") == ("Madonna", "")


def test_split_full_name_string_vazia_nao_quebra():
    assert split_full_name("") == ("", "")
    assert split_full_name("   ") == ("", "")


def test_split_full_name_limpa_espacos_ao_redor():
    assert split_full_name("  Daniel Pilar  ") == ("Daniel", "Pilar")
