# Generated by Django 2.1.7 on 2019-03-28 20:39

import django.contrib.postgres.fields.citext
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('beers', '0020_prepare_for_case_insensitive_alt_names'),
    ]

    operations = [
        migrations.AlterField(
            model_name='beeralternatename',
            name='name',
            field=django.contrib.postgres.fields.citext.CITextField(),
        ),
        migrations.AlterField(
            model_name='manufactureralternatename',
            name='name',
            field=django.contrib.postgres.fields.citext.CITextField(),
        ),
    ]
