from csv import writer

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse, HttpResponseRedirect

from . import models


class BeerAlternateNameInline(admin.TabularInline):
    model = models.BeerAlternateName


class BeerAdmin(admin.ModelAdmin):

    def export_as_csv(self, request, queryset):
        queryset = queryset.select_related(
            'manufacturer', 'style',
        ).annotate(taps_count=Count('taps')).prefetch_related(
            'alternate_names',
        ).order_by(
            'manufacturer__name', 'name',
        )
        field_names = {
            'ID': 'id',
            'Name': 'name',
            'Manufacturer': 'manufacturer',
            'Style': 'style',
            'Taps occupied': 'taps_count',
        }
        most_alt_names = max(len(i.alternate_names.all()) for i in queryset)
        header = list(field_names.keys()) + [
            'Alternate Names',
        ] + ([''] * (most_alt_names - 1))

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(
            queryset.model._meta)
        csv_writer = writer(response)

        csv_writer.writerow(header)
        for obj in queryset:
            alt_names = [i.name for i in obj.alternate_names.all()]
            padding = [''] * (most_alt_names - len(alt_names))
            csv_writer.writerow(
                [
                    getattr(obj, val) if val in {'id', 'taps_count'}
                    else str(getattr(obj, val)) for val in field_names.values()
                ] + alt_names + padding,
            )
        return response

    def merge_beers(self, request, queryset):
        """
        Merge multiple beers into one.

        Takes the best guess as to which beer to keep based on these criteria:
        1. If one beer has a color and the others don't, keep it.
        2. If one beer has more *_url fields set than the others, keep it.
           In case of a tie, the beer that's on tap at more places is kept.
           In case that's tied, use lowest PK as a tiebreaker.
        3. If neither of the above is set, keep the one with the lowest PK.
        """
        beers = list(queryset)
        if len(beers) == 1:
            self.message_user(
                request,
                message='Nothing to do; you only selected one beer.',
            )
            return
        keeper = None
        beers_with_color = [
            i for i in beers if i.color_srm or i.color_html
        ]
        if len(beers_with_color) == 1:
            keeper = beers_with_color[0]
        else:
            fields = [
                i.name for i in beers[0]._meta.fields if i.name.endswith('_url')
            ]
            max_url_fields_set = -1
            most_places_on_tap = -1
            for beer in beers:
                fields_set = sum(
                    bool(getattr(beer, field)) for field in fields
                )
                if fields_set > max_url_fields_set:
                    max_url_fields_set = fields_set
                    keeper = beer
                    most_places_on_tap = beer.taps.count()
                elif fields_set == max_url_fields_set:
                    # use number of taps occupied as a tiebreaker
                    places_on_tap = beer.taps.count()
                    if places_on_tap > most_places_on_tap or (
                            places_on_tap == most_places_on_tap and
                            beer.id < keeper.id
                    ):
                        max_url_fields_set = fields_set
                        keeper = beer
                        most_places_on_tap = places_on_tap
        if not keeper:
            self.message_user(
                request,
                message='Unable to determine which beer to keep!',
                level=messages.ERROR,
            )
            return
        with transaction.atomic():
            for beer in beers:
                if beer == keeper:
                    continue
                keeper.merge_from(beer)
        self.message_user(
            request,
            message=f'Merged {", ".join(str(i) for i in beers if i != keeper)} into '
            f'{keeper}'
        )

    merge_beers.short_description = 'Merge beers'
    export_as_csv.short_description = 'Export as CSV'
    actions = ['merge_beers', 'export_as_csv']
    list_display = ('name', 'manufacturer', 'id')
    list_filter = ('name', 'manufacturer')
    list_select_related = ('manufacturer', )
    search_fields = ('name', 'manufacturer__name')
    inlines = [BeerAlternateNameInline]


class ManufacturerAlternateNameInline(admin.TabularInline):
    model = models.ManufacturerAlternateName


class ManufacturerAdmin(admin.ModelAdmin):

    def url_fields_set(self, manufacturer):
        fields = [
            i.name
            for i in manufacturer._meta.fields
            if i.name.endswith('_url')
        ]
        return sum(
            bool(
                getattr(manufacturer, field)
            ) for field in fields
        )

    def merge_manufacturers(self, request, queryset):
        """
        Merge multiple manufacturers into one.

        Takes the best guess as to which mfg to keep based on these criteria:
        1. MFG with the most beers gets the nod.
        2. If tied, mfg with the most *_url fields gets the nod.`
        3. If still tied, lowest PK wins.
        """
        manufacturers = list(queryset)
        if len(manufacturers) == 1:
            self.message_user(
                request,
                message='Nothing to do; you only selected one manufacturer.',
            )
            return
        keeper = None
        most_beers = -1
        most_url_fields_set = -1
        for manufacturer in manufacturers:
            beers = manufacturer.beers.count()
            url_fields_set = self.url_fields_set(manufacturer)
            if beers > most_beers or (beers == most_beers and (
                    url_fields_set > most_url_fields_set
            ) or (
                    url_fields_set == most_url_fields_set and
                    manufacturer.id < keeper.id
            )):
                keeper = manufacturer
                most_url_fields_set = url_fields_set
                most_beers = beers
        if not keeper:
            self.message_user(
                request,
                message='Unable to determine which manufacturer to keep!',
                level=messages.ERROR,
            )
            return
        with transaction.atomic():
            for manufacturer in manufacturers:
                if manufacturer == keeper:
                    continue
                keeper.merge_from(manufacturer)
        self.message_user(
            request,
            message=f'Merged {", ".join(str(i) for i in manufacturers if i != keeper)} into '
            f'{manufacturer}'
        )

    inlines = [ManufacturerAlternateNameInline]
    merge_manufacturers.short_description = 'Merge manufacturers'
    actions = ['merge_manufacturers']
    list_display = ('name', 'id')
    list_filter = ('name', )
    search_fields = ('name', )


class BeerAlternateNameAdmin(admin.ModelAdmin):
    list_display = ('name', 'beer', 'id')
    list_select_related = ('beer', 'beer__manufacturer')
    list_filter = ('beer__name', 'beer__manufacturer__name')
    search_fields = ('name', 'beer__name', 'beer__manufacturer__name')


class ManufacturerAlternateNameAdmin(admin.ModelAdmin):
    list_display = ('name', 'manufacturer')
    list_select_related = ('manufacturer', )
    search_fields = ('name', 'manufacturer__name')


class BeerPriceAdmin(admin.ModelAdmin):
    list_display = ('beer', 'serving_size', 'venue', 'price', 'id')
    list_select_related = ('beer', 'venue', 'serving_size')
    search_fields = ('beer__name', 'serving_size__name', )


class StyleAlternateNameInline(admin.TabularInline):
    model = models.StyleAlternateName


class StyleAdmin(admin.ModelAdmin):
    inlines = [StyleAlternateNameInline]
    actions = ['export_as_csv', 'merge_styles']
    search_fields = ('name', 'alternate_names__name')
    list_display = ('name', 'id')

    def merge_styles(self, request, queryset):
        selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect(
            f"/beers/mergestyles/?ids={','.join(selected)}",
        )

    def export_as_csv(self, request, queryset):
        queryset = queryset.prefetch_related(
            'alternate_names',
        ).annotate(names_count=Count('alternate_names__name'))
        meta = self.model._meta
        most_alt_names = max(i.names_count for i in queryset)
        field_names = [field.name for field in meta.fields]
        header = field_names + [
            'Alternate Names',
        ] + ([''] * (most_alt_names - 1))

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(
            meta)
        csv_writer = writer(response)

        csv_writer.writerow(header)
        for obj in queryset:
            alt_names = [i.name for i in obj.alternate_names.all()]
            padding = [''] * (most_alt_names - len(alt_names))
            csv_writer.writerow(
                [
                    getattr(obj, field) for field in field_names
                ] + alt_names + padding,
            )
        return response


admin.site.register(models.Style, StyleAdmin)
admin.site.register(models.Manufacturer, ManufacturerAdmin)
admin.site.register(models.BeerPrice, BeerPriceAdmin)
admin.site.register(models.ServingSize)
admin.site.register(models.BeerAlternateName, BeerAlternateNameAdmin)
admin.site.register(
    models.ManufacturerAlternateName, ManufacturerAlternateNameAdmin)
admin.site.register(models.Beer, BeerAdmin)
admin.site.register(models.UntappdMetadata)
